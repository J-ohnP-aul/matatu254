from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Count

from fleet.models import Matatu
from trips.models import ActiveTrip
from journeys.models import JourneySession
from notifications.models import Notification


def _get_assigned_matatu(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return None

    matatu = getattr(user, 'matatu', None)
    if matatu:
        return matatu

    return Matatu.objects.filter(conductor=user).first() or user.matatus.first()


def _is_authorized_conductor(user, matatu):
    if not user or not matatu or getattr(user, 'role', None) != 'CONDUCTOR':
        return False

    if getattr(user, 'matatu_id', None) == matatu.pk:
        return True

    if getattr(matatu, 'owner_id', None) == user.pk:
        return True

    return matatu.conductor.filter(pk=user.pk).exists()


@login_required
def dashboard(request):
    """Conductor main dashboard - shows active trip for their matatu"""
    if request.user.role != 'CONDUCTOR':
        return render(request, "conductor/not_conductor.html")
    
    # Get the matatu assigned to this conductor via either direct assignment or reverse relation
    matatu = _get_assigned_matatu(request.user)
    
    active_trip = None
    if matatu:
        active_trip = ActiveTrip.objects.filter(
            matatu=matatu,
            status=ActiveTrip.Status.ACTIVE
        ).first()
    
    context = {
        "matatu": matatu,
        "active_trip": active_trip,
    }
    return render(request, "conductor/dashboard.html", context)


@login_required
def trip_detail(request, trip_id):
    """Detailed view of active trip with passenger info"""
    if request.user.role != 'CONDUCTOR':
        return render(request, "conductor/not_conductor.html")
    
    trip = get_object_or_404(ActiveTrip, pk=trip_id)
    
    # Verify conductor is assigned to this trip's matatu through either ownership path
    if not _is_authorized_conductor(request.user, trip.matatu):
        return render(request, "conductor/not_authorized.html")
    
    # Get all journey sessions for this trip
    journeys = JourneySession.objects.filter(trip=trip).select_related(
        'passenger', 'destination_stage'
    ).order_by('destination_stage__sequence_order')
    
    # Aggregate passenger counts per destination stage
    stage_counts = journeys.values(
        'destination_stage__name', 
        'destination_stage__sequence_order',
        'destination_stage_id'
    ).annotate(count=Count('id')).order_by('destination_stage__sequence_order')
    
    # Current vehicle position
    vehicle_pos = None
    if trip.current_latitude and trip.current_longitude:
        vehicle_pos = (float(trip.current_latitude), float(trip.current_longitude))
    
    # Find current and next stage
    from r_outes.routes_services import is_near_stage
    route_stages = list(trip.route.stages.order_by("sequence_order"))
    current_stage = None
    next_stage = None
    
    if vehicle_pos:
        for stage in route_stages:
            if is_near_stage(vehicle_pos[0], vehicle_pos[1], stage):
                current_stage = stage
            elif next_stage is None:
                next_stage = stage
    
    # Upcoming stops with passenger counts
    upcoming_stops = []
    for sc in stage_counts:
        stage_id = sc['destination_stage_id']
        stage = next((s for s in route_stages if s.id == stage_id), None)
        if stage:
            is_next = next_stage and stage.id == next_stage.id
            is_current = current_stage and stage.id == current_stage.id
            upcoming_stops.append({
                'stage': stage,
                'count': sc['count'],
                'is_next': is_next,
                'is_current': is_current,
            })
    
    context = {
        "trip": trip,
        "journeys": journeys,
        "upcoming_stops": upcoming_stops,
        "current_stage": current_stage,
        "next_stage": next_stage,
        "total_passengers": journeys.count(),
        "vehicle_pos": vehicle_pos,
    }
    return render(request, "conductor/trip_detail.html", context)


@login_required
def trip_passengers(request, trip_id):
    """HTMX partial - passenger list for a trip"""
    trip = get_object_or_404(ActiveTrip, pk=trip_id)
    if not _is_authorized_conductor(request.user, trip.matatu):
        return render(request, "conductor/not_authorized.html")

    journeys = JourneySession.objects.filter(trip=trip).select_related(
        'passenger', 'destination_stage'
    ).order_by('destination_stage__sequence_order')
    
    return render(request, "conductor/partials/passenger_list.html", {
        "journeys": journeys,
    })


@login_required
def notifications(request):
    """Conductor notifications"""
    if request.user.role != 'CONDUCTOR':
        return render(request, "conductor/not_conductor.html")
    
    notifications = Notification.objects.filter(
        recipient_type=Notification.RecipientType.CONDUCTOR,
        recipient_id=request.user.id
    ).order_by('-timestamp')[:50]
    
    return render(request, "conductor/notifications.html", {
        "notifications": notifications,
    })