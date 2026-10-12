from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db.models import Count
from django.utils import timezone

from fleet.models import Matatu, QRCode
from r_outes.models import Route, Stage
from trips.models import ActiveTrip
from journeys.models import JourneySession
from notifications.models import Notification
from core.models import SystemConfig


def is_admin(user):
    return user.is_authenticated and user.role == 'ADMIN'


@login_required
@user_passes_test(is_admin)
def dashboard(request):
    """Admin dashboard overview"""
    stats = {
        'total_matatus': Matatu.objects.count(),
        'active_trips': ActiveTrip.objects.filter(status=ActiveTrip.Status.ACTIVE).count(),
        'total_routes': Route.objects.count(),
        'total_stages': Stage.objects.count(),
        'total_passengers': JourneySession.objects.values('passenger').distinct().count(),
        'pending_notifications': Notification.objects.filter(status=Notification.Status.SENT).count(),
    }
    recent_trips = ActiveTrip.objects.select_related('matatu', 'route').order_by('-start_time')[:10]
    return render(request, "management/dashboard.html", {
        'stats': stats,
        'recent_trips': recent_trips,
    })


# ===== MATATU MANAGEMENT =====

@login_required
@user_passes_test(is_admin)
def matatu_list(request):
    matatus = Matatu.objects.annotate(
        trip_count=Count('activetrip'),
        qr_status=Count('qr_code')
    ).order_by('-created_at')
    return render(request, "management/matatu_list.html", {'matatus': matatus})


@login_required
@user_passes_test(is_admin)
def matatu_create(request):
    if request.method == 'POST':
        registration = request.POST.get('registration_number', '').strip().upper()
        operator = request.POST.get('operator', '').strip()
        owner_id = request.POST.get('owner')
        
        if not registration or not operator:
            messages.error(request, "Registration number and operator are required")
        else:
            matatu = Matatu.objects.create(
                registration_number=registration,
                operator=operator,
                owner_id=owner_id if owner_id else None
            )
            # Auto-create QR code
            QRCode.objects.create(
                matatu=matatu,
                code_value=f"MAT-{matatu.id:04d}",
                status=QRCode.Status.ACTIVE
            )
            messages.success(request, f"Matatu {registration} created with QR code")
            return redirect('management:matatu-list')
    
    from accounts.models import User
    conductors = User.objects.filter(role=User.CONDUCTOR)
    return render(request, "management/matatu_form.html", {
        'conductors': conductors,
        'action': 'Create'
    })


@login_required
@user_passes_test(is_admin)
def matatu_edit(request, pk):
    matatu = get_object_or_404(Matatu, pk=pk)
    if request.method == 'POST':
        matatu.registration_number = request.POST.get('registration_number', '').strip().upper()
        matatu.operator = request.POST.get('operator', '').strip()
        owner_id = request.POST.get('owner')
        matatu.owner_id = owner_id if owner_id else None
        matatu.save()
        messages.success(request, "Matatu updated")
        return redirect('management:matatu-list')
    
    from accounts.models import User
    conductors = User.objects.filter(role=User.CONDUCTOR)
    return render(request, "management/matatu_form.html", {
        'matatu': matatu,
        'conductors': conductors,
        'action': 'Edit'
    })


@login_required
@user_passes_test(is_admin)
def matatu_qr(request, pk):
    matatu = get_object_or_404(Matatu, pk=pk)
    qr, created = QRCode.objects.get_or_create(
        matatu=matatu,
        defaults={'code_value': f"MAT-{matatu.id:04d}", 'status': QRCode.Status.ACTIVE}
    )
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'regenerate':
            qr.code_value = f"MAT-{matatu.id:04d}-{timezone.now().strftime('%Y%m%d%H%M')}"
            qr.status = QRCode.Status.ACTIVE
            qr.save()
            messages.success(request, "QR code regenerated")
        elif action == 'toggle':
            qr.status = QRCode.Status.INACTIVE if qr.status == QRCode.Status.ACTIVE else QRCode.Status.ACTIVE
            qr.save()
            messages.success(request, f"QR code {'activated' if qr.status == QRCode.Status.ACTIVE else 'deactivated'}")
        return redirect('management:matatu-qr', pk=pk)
    
    # Generate QR image for display
    import qrcode
    from io import BytesIO
    import base64
    qr_img = qrcode.make(qr.code_value)
    buffer = BytesIO()
    qr_img.save(buffer, format='PNG')
    qr_b64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    return render(request, "management/matatu_qr.html", {
        'matatu': matatu,
        'qr': qr,
        'qr_b64': qr_b64,
    })


# ===== ROUTE MANAGEMENT =====

@login_required
@user_passes_test(is_admin)
def route_list(request):
    routes = Route.objects.annotate(
        stages_count=Count('stages'),
        trip_count=Count('activetrip')
    ).order_by('name')
    return render(request, "management/route_list.html", {'routes': routes})


@login_required
@user_passes_test(is_admin)
def route_create(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        if not name:
            messages.error(request, "Route name is required")
        else:
            route = Route.objects.create(name=name, description=description)
            messages.success(request, f"Route '{name}' created")
            return redirect('management:route-stages', pk=route.pk)
    return render(request, "management/route_form.html", {'action': 'Create'})


@login_required
@user_passes_test(is_admin)
def route_edit(request, pk):
    route = get_object_or_404(Route, pk=pk)
    if request.method == 'POST':
        route.name = request.POST.get('name', '').strip()
        route.description = request.POST.get('description', '').strip()
        route.save()
        messages.success(request, "Route updated")
        return redirect('management:route-list')
    return render(request, "management/route_form.html", {'route': route, 'action': 'Edit'})


@login_required
@user_passes_test(is_admin)
def route_stages(request, pk):
    route = get_object_or_404(Route, pk=pk)
    stages = route.stages.order_by('sequence_order')
    return render(request, "management/route_stages.html", {'route': route, 'stages': stages})


@login_required
@user_passes_test(is_admin)
def stage_create(request, pk):
    route = get_object_or_404(Route, pk=pk)
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        sequence_order = request.POST.get('sequence_order')
        latitude = request.POST.get('latitude')
        longitude = request.POST.get('longitude')
        
        if not all([name, sequence_order, latitude, longitude]):
            messages.error(request, "All fields are required")
        else:
            Stage.objects.create(
                route=route,
                name=name,
                sequence_order=int(sequence_order),
                latitude=latitude,
                longitude=longitude,
            )
            messages.success(request, f"Stage '{name}' added")
            return redirect('management:route-stages', pk=route.pk)
    
    # Suggest next sequence order
    next_order = (route.stages.aggregate(max_order=models.Max('sequence_order'))['max_order'] or 0) + 1
    return render(request, "management/stage_form.html", {
        'route': route,
        'next_order': next_order,
        'action': 'Create'
    })


@login_required
@user_passes_test(is_admin)
def stage_edit(request, pk):
    stage = get_object_or_404(Stage, pk=pk)
    if request.method == 'POST':
        stage.name = request.POST.get('name', '').strip()
        stage.sequence_order = int(request.POST.get('sequence_order'))
        stage.latitude = request.POST.get('latitude')
        stage.longitude = request.POST.get('longitude')
        stage.save()
        messages.success(request, "Stage updated")
        return redirect('management:route-stages', pk=stage.route.pk)
    return render(request, "management/stage_form.html", {
        'stage': stage,
        'route': stage.route,
        'action': 'Edit'
    })


@login_required
@user_passes_test(is_admin)
def stage_delete(request, pk):
    stage = get_object_or_404(Stage, pk=pk)
    route_pk = stage.route.pk
    if request.method == 'POST':
        stage.delete()
        messages.success(request, "Stage deleted")
    return redirect('management:route-stages', pk=route_pk)


# ===== TRIP MANAGEMENT =====

@login_required
@user_passes_test(is_admin)
def trip_list(request):
    trips = ActiveTrip.objects.select_related('matatu', 'route').order_by('-start_time')
    return render(request, "management/trip_list.html", {'trips': trips})


@login_required
@user_passes_test(is_admin)
def trip_create(request):
    if request.method == 'POST':
        matatu_id = request.POST.get('matatu')
        route_id = request.POST.get('route')
        status = request.POST.get('status', ActiveTrip.Status.CREATED)
        
        if not matatu_id or not route_id:
            messages.error(request, "Matatu and route are required")
        else:
            trip = ActiveTrip.objects.create(
                matatu_id=matatu_id,
                route_id=route_id,
                status=status,
            )
            messages.success(request, f"Trip created for {trip.matatu}")
            return redirect('management:trip-list')
    
    matatus = Matatu.objects.all()
    routes = Route.objects.all()
    return render(request, "management/trip_form.html", {
        'matatus': matatus,
        'routes': routes,
        'status_choices': ActiveTrip.Status.choices,
        'action': 'Create'
    })


@login_required
@user_passes_test(is_admin)
def trip_start(request, pk):
    trip = get_object_or_404(ActiveTrip, pk=pk)
    if trip.status == ActiveTrip.Status.CREATED:
        trip.status = ActiveTrip.Status.ACTIVE
        trip.start_time = timezone.now()
        trip.save()
        messages.success(request, "Trip started")
    else:
        messages.error(request, "Trip cannot be started from current status")
    return redirect('management:trip-list')


@login_required
@user_passes_test(is_admin)
def trip_end(request, pk):
    trip = get_object_or_404(ActiveTrip, pk=pk)
    if trip.status == ActiveTrip.Status.ACTIVE:
        trip.status = ActiveTrip.Status.COMPLETED
        trip.end_time = timezone.now()
        trip.save()
        # End all journey sessions
        JourneySession.objects.filter(trip=trip).exclude(
            status=JourneySession.Status.ENDED
        ).update(status=JourneySession.Status.ENDED, end_time=timezone.now())
        messages.success(request, "Trip ended")
    else:
        messages.error(request, "Trip cannot be ended from current status")
    return redirect('management:trip-list')


@login_required
@user_passes_test(is_admin)
def trip_cancel(request, pk):
    trip = get_object_or_404(ActiveTrip, pk=pk)
    if trip.status in [ActiveTrip.Status.CREATED, ActiveTrip.Status.ACTIVE]:
        trip.status = ActiveTrip.Status.CANCELLED
        trip.end_time = timezone.now()
        trip.save()
        messages.success(request, "Trip cancelled")
    else:
        messages.error(request, "Trip cannot be cancelled from current status")
    return redirect('management:trip-list')


# ===== SYSTEM CONFIG =====

@login_required
@user_passes_test(is_admin)
def system_config(request):
    configs = SystemConfig.objects.all().order_by('key')
    if request.method == 'POST':
        key = request.POST.get('key', '').strip()
        value = request.POST.get('value', '').strip()
        if key:
            SystemConfig.objects.update_or_create(key=key, defaults={'value': value})
            messages.success(request, f"Config '{key}' saved")
        return redirect('management:system-config')
    return render(request, "management/system_config.html", {'configs': configs})


@login_required
@user_passes_test(is_admin)
def system_config_edit(request, pk):
    config = get_object_or_404(SystemConfig, pk=pk)
    if request.method == 'POST':
        config.value = request.POST.get('value', '').strip()
        config.save()
        messages.success(request, "Config updated")
        return redirect('management:system-config')
    return render(request, "management/system_config_form.html", {'config': config})

# Need to import models for stage_create
from django.db import models