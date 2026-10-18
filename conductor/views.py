from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import JsonResponse

from fleet.models import Matatu
from trips.models import ActiveTrip
from journeys.models import JourneySession
from notifications.models import Notification
from r_outes.routes_services import is_near_stage, remaining_road_distance, get_route_polyline
from core.geo import haversine_distance_m
from tracking.models import TripLocationLog


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
    stage_counts = []
    total_passengers = 0
    if matatu:
        active_trip = ActiveTrip.objects.filter(
            matatu=matatu,
            status=ActiveTrip.Status.ACTIVE
        ).first()

    if active_trip:
        active_statuses = [
            JourneySession.Status.DESTINATION_SELECTED,
            JourneySession.Status.IN_TRANSIT,
            JourneySession.Status.APPROACHING,
            JourneySession.Status.ARRIVED,
        ]
        grouped_counts = {
            row['destination_stage_id']: row['count']
            for row in JourneySession.objects.filter(
                trip=active_trip, status__in=active_statuses
            ).values('destination_stage_id').annotate(count=Count('id'))
        }
        stage_counts = [
            {'stage': stage, 'count': grouped_counts.get(stage.pk, 0)}
            for stage in active_trip.route.stages.order_by('sequence_order')
        ]
        total_passengers = sum(row['count'] for row in stage_counts)
    
    context = {
        "matatu": matatu,
        "active_trip": active_trip,
        "stage_counts": stage_counts,
        "total_passengers": total_passengers,
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
    active_statuses = [
        JourneySession.Status.DESTINATION_SELECTED,
        JourneySession.Status.IN_TRANSIT,
        JourneySession.Status.APPROACHING,
        JourneySession.Status.ARRIVED,
    ]
    journeys = JourneySession.objects.filter(
        trip=trip,
        status__in=[
            JourneySession.Status.DESTINATION_SELECTED,
            JourneySession.Status.IN_TRANSIT,
            JourneySession.Status.APPROACHING,
            JourneySession.Status.ARRIVED,
        ],
    ).select_related('passenger', 'destination_stage').order_by('destination_stage__sequence_order')
    onboard_journeys = journeys.filter(status__in=active_statuses)
    
    # Aggregate passenger counts per destination stage
    stage_counts = onboard_journeys.values(
        'destination_stage__name', 
        'destination_stage__sequence_order',
        'destination_stage_id'
    ).annotate(count=Count('id')).order_by('destination_stage__sequence_order')
    
    route_stages = list(trip.route.stages.order_by("sequence_order"))
    tracking = _get_trip_tracking_snapshot(trip, route_stages)
    current_stage = tracking["current_stage"]
    next_stage = tracking["next_stage"]
    counts_by_stage = {row["destination_stage_id"]: row["count"] for row in stage_counts}
    
    # Show each route stop, even when nobody is currently due to alight there.
    upcoming_stops = []
    for stage in route_stages:
        is_next = next_stage and stage.id == next_stage.id
        is_current = current_stage and stage.id == current_stage.id
        upcoming_stops.append({
            'stage': stage,
            'count': counts_by_stage.get(stage.id, 0),
            'is_next': is_next,
            'is_current': is_current,
            'alighting_count': counts_by_stage.get(stage.id, 0),
        })
    
    context = {
        "trip": trip,
        "journeys": journeys,
        "upcoming_stops": upcoming_stops,
        "current_stage": current_stage,
        "next_stage": next_stage,
        "total_passengers": onboard_journeys.count(),
        "vehicle_pos": tracking["vehicle_pos"],
        "trip_destination": tracking["destination"],
        "remaining": tracking["remaining"],
        "next_stage_remaining": tracking["next_stage_remaining"],
        "speed_kmh": tracking["speed_kmh"],
        "progress_percent": tracking["progress_percent"],
        "gps_stale": trip.is_stale,
        "gps_age_seconds": trip.gps_age_seconds,
        "alighting_count": counts_by_stage.get(next_stage.id, 0) if next_stage else 0,
        "at_destination": tracking["at_destination"],
    }
    return render(request, "conductor/trip_detail.html", context)


@login_required
def trip_tracking_data(request, trip_id):
    """Return the latest authorized trip position, stage, distance and ETA."""
    trip = get_object_or_404(ActiveTrip, pk=trip_id)
    if not _is_authorized_conductor(request.user, trip.matatu):
        return JsonResponse({"error": "Not authorized for this trip"}, status=403)

    route_stages = list(trip.route.stages.order_by("sequence_order"))
    tracking = _get_trip_tracking_snapshot(trip, route_stages)
    remaining = tracking["remaining"]
    vehicle_pos = tracking["vehicle_pos"]

    return JsonResponse({
        "destination": tracking["destination"].name if tracking["destination"] else None,
        "current_stage": tracking["current_stage"].name if tracking["current_stage"] else None,
        "current_stage_order": tracking["current_stage"].sequence_order if tracking["current_stage"] else None,
        "next_stage": tracking["next_stage"].name if tracking["next_stage"] else None,
        "next_stage_order": tracking["next_stage"].sequence_order if tracking["next_stage"] else None,
        "vehicle_latitude": vehicle_pos[0] if vehicle_pos else None,
        "vehicle_longitude": vehicle_pos[1] if vehicle_pos else None,
        "at_destination": tracking["at_destination"],
        "progress_percent": tracking["progress_percent"],
        "next_stage_distance_m": tracking["next_stage_remaining"].distance_m if tracking["next_stage_remaining"] else None,
        "next_stage_duration_minutes": tracking["next_stage_remaining"].duration_minutes if tracking["next_stage_remaining"] else None,
        "speed_kmh": tracking["speed_kmh"],
        "total_passengers": JourneySession.objects.filter(
            trip=trip,
            status__in=[
                JourneySession.Status.DESTINATION_SELECTED,
                JourneySession.Status.IN_TRANSIT,
                JourneySession.Status.APPROACHING,
                JourneySession.Status.ARRIVED,
            ],
        ).count(),
        "alighting_counts": {
            str(row["destination_stage__sequence_order"]): row["count"]
            for row in JourneySession.objects.filter(
                trip=trip,
                status__in=[
                    JourneySession.Status.DESTINATION_SELECTED,
                    JourneySession.Status.IN_TRANSIT,
                    JourneySession.Status.APPROACHING,
                    JourneySession.Status.ARRIVED,
                ],
            ).values("destination_stage__sequence_order").annotate(count=Count("id"))
        },
        "distance_m": remaining.distance_m if remaining else None,
        "distance_km": remaining.distance_km if remaining else None,
        "duration_s": remaining.duration_s if remaining else None,
        "duration_minutes": remaining.duration_minutes if remaining else None,
        "gps_stale": trip.is_stale,
        "gps_age_seconds": trip.gps_age_seconds,
        "last_ping_at": trip.last_ping_at.isoformat() if trip.last_ping_at else None,
    })


def _get_trip_tracking_snapshot(trip, route_stages):
    """Calculate trip-level remaining distance to the route's final stage."""
    vehicle_pos = None
    if trip.current_latitude is not None and trip.current_longitude is not None:
        vehicle_pos = (float(trip.current_latitude), float(trip.current_longitude))

    destination = route_stages[-1] if route_stages else None
    current_stage = None
    if vehicle_pos:
        for stage in route_stages:
            if is_near_stage(vehicle_pos[0], vehicle_pos[1], stage):
                current_stage = stage

    if current_stage:
        next_stage = next(
            (stage for stage in route_stages
             if stage.sequence_order > current_stage.sequence_order),
            None,
        )
    else:
        next_stage = route_stages[0] if route_stages else None

    at_destination = bool(current_stage and destination and current_stage.id == destination.id)
    remaining = None
    if vehicle_pos and next_stage and destination:
        remaining = remaining_road_distance(vehicle_pos, next_stage, destination)
    next_stage_remaining = None
    if vehicle_pos and next_stage:
        next_stage_remaining = remaining_road_distance(vehicle_pos, next_stage, next_stage)

    progress_percent = 0
    if destination and current_stage:
        stages_before_destination = [stage for stage in route_stages if stage.sequence_order <= destination.sequence_order]
        if len(stages_before_destination) <= 1:
            progress_percent = 100
        else:
            progress_percent = round(
                next((index for index, stage in enumerate(stages_before_destination) if stage.id == current_stage.id), 0)
                / (len(stages_before_destination) - 1) * 100
            )

    speed_kmh = _get_recent_speed_kmh(trip)

    return {
        "vehicle_pos": vehicle_pos,
        "destination": destination,
        "current_stage": current_stage,
        "next_stage": next_stage,
        "remaining": remaining,
        "next_stage_remaining": next_stage_remaining,
        "progress_percent": progress_percent,
        "speed_kmh": speed_kmh,
        "at_destination": at_destination,
    }


def _get_recent_speed_kmh(trip):
    """Estimate current speed from the two newest GPS pings when plausible."""
    pings = list(
        TripLocationLog.objects.filter(trip=trip)
        .order_by("-recorded_at", "-pk")[:2]
    )
    if len(pings) < 2:
        return None
    elapsed_s = (pings[0].recorded_at - pings[1].recorded_at).total_seconds()
    if elapsed_s <= 0:
        return None
    distance_m = haversine_distance_m(
        float(pings[1].latitude), float(pings[1].longitude),
        float(pings[0].latitude), float(pings[0].longitude),
    )
    speed_kmh = distance_m / elapsed_s * 3.6
    return round(speed_kmh, 1) if speed_kmh <= 160 else None


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


@login_required
def trip_route_data(request, trip_id):
    """Return route polyline and stage data for the conductor map."""
    trip = get_object_or_404(ActiveTrip, pk=trip_id)
    if not _is_authorized_conductor(request.user, trip.matatu):
        return JsonResponse({"error": "Not authorized for this trip"}, status=403)
    
    # Get all stages for this route
    stages = list(trip.route.stages.order_by("sequence_order").values(
        'id', 'name', 'latitude', 'longitude', 'sequence_order'
    ))
    
    # Get route polyline from OSRM (full route)
    try:
        origin = (float(trip.route.stages.first().longitude), float(trip.route.stages.first().latitude))
        destination = (float(trip.route.stages.last().longitude), float(trip.route.stages.last().latitude))
        polyline = get_route_polyline(origin, destination)
    except Exception:
        polyline = None
    
    return JsonResponse({
        "polyline": polyline,
        "stages": list(stages),
    })
