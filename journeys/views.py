from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from fleet.models import QRCode
from trips.models import ActiveTrip
from r_outes.models import Stage
from journeys.models import JourneySession
from notifications.models import Notification
from journeys.services import (
    create_journey_session,
    get_active_journey,
    update_journey_status,
    calculate_remaining,
    end_journey,
)
from r_outes.routes_services import is_near_stage


def scan_qr(request):
    """Render the camera scanner page"""
    if request.user.is_authenticated:
        active_journey = get_active_journey(request.user)
        if active_journey:
            return redirect("journeys:journey-detail", journey_id=active_journey.pk)
    return render(request, "journeys/scan.html")


def scan_result(request):
    """Process scanned QR code_value"""
    if request.method != "POST":
        return redirect("journeys:scan-qr")

    if request.user.is_authenticated:
        active_journey = get_active_journey(request.user)
        if active_journey:
            return redirect("journeys:journey-detail", journey_id=active_journey.pk)

    code_value = request.POST.get("code_value", "").strip()
    if not code_value:
        messages.error(request, "No QR code data received")
        return redirect("journeys:scan-qr")

    qr = get_object_or_404(QRCode, code_value=code_value, status=QRCode.Status.ACTIVE)
    matatu = qr.matatu
    trip = ActiveTrip.objects.filter(
        matatu=matatu,
        status=ActiveTrip.Status.ACTIVE
    ).first()

    if not trip:
        messages.error(request, "This matatu has no active trip right now")
        return redirect("journeys:scan-qr")

    return redirect("journeys:trip-stages", trip_id=trip.id)


def trip_stages(request, trip_id):
    trip = get_object_or_404(ActiveTrip, pk=trip_id, status=ActiveTrip.Status.ACTIVE)
    stages = trip.route.stages.order_by("sequence_order")
    return render(request, "journeys/stages.html", {"trip": trip, "stages": stages})


@login_required
def select_destination(request, trip_id):
    trip = get_object_or_404(ActiveTrip, pk=trip_id, status=ActiveTrip.Status.ACTIVE)
    active_journey = get_active_journey(request.user)
    if active_journey:
        return redirect("journeys:journey-detail", journey_id=active_journey.pk)
    
    if request.method == "POST":
        stage_id = request.POST.get("destination_stage_id")
        stage = get_object_or_404(Stage, pk=stage_id, route=trip.route)
        
        journey = create_journey_session(request.user, trip, stage)
        return redirect("journeys:journey-detail", journey_id=journey.id)
    
    stages = trip.route.stages.order_by("sequence_order")
    return render(request, "journeys/stages.html", {"trip": trip, "stages": stages})


@login_required
def journey_detail(request, journey_id):
    journey = get_object_or_404(JourneySession, pk=journey_id, passenger=request.user)
    
    # Update status based on vehicle position
    journey = update_journey_status(journey)
    
    trip = journey.trip
    route_stages = list(trip.route.stages.order_by("sequence_order"))
    tracking = _get_tracking_snapshot(journey, route_stages)
    passenger_stages = [
        stage for stage in route_stages
        if stage.sequence_order <= journey.destination_stage.sequence_order
    ]
    progress_percent = _get_progress_percent(passenger_stages, tracking["current_stage"])
    latest_notification = _latest_journey_notification(journey)
    
    return render(request, "journeys/tracking.html", {
        "journey": journey,
        "trip": trip,
        "current_stage": tracking["current_stage"],
        "next_stage": tracking["next_stage"],
        "destination": journey.destination_stage,
        "remaining": tracking["remaining"],
        "route_stages": passenger_stages,
        "progress_percent": progress_percent,
        "latest_notification": latest_notification,
    })


@login_required
def journey_tracking_data(request, journey_id):
    """Return the latest journey distance and ETA for the tracking page."""
    journey = get_object_or_404(JourneySession, pk=journey_id, passenger=request.user)
    journey = update_journey_status(journey)
    route_stages = list(journey.trip.route.stages.order_by("sequence_order"))
    tracking = _get_tracking_snapshot(journey, route_stages)
    remaining = tracking["remaining"]
    latest_notification = _latest_journey_notification(journey)

    return JsonResponse({
        "status": journey.get_status_display(),
        "current_stage": tracking["current_stage"].name if tracking["current_stage"] else None,
        "current_stage_order": tracking["current_stage"].sequence_order if tracking["current_stage"] else None,
        "progress_percent": tracking["progress_percent"],
        "next_stage": tracking["next_stage"].name if tracking["next_stage"] else None,
        "next_stage_order": tracking["next_stage"].sequence_order if tracking["next_stage"] else None,
        "at_destination": bool(
            tracking["current_stage"]
            and tracking["current_stage"].id == journey.destination_stage_id
        ),
        "distance_m": remaining.distance_m if remaining else None,
        "distance_km": remaining.distance_km if remaining else None,
        "duration_s": remaining.duration_s if remaining else None,
        "duration_minutes": remaining.duration_minutes if remaining else None,
        "latest_notification": {
            "id": latest_notification.pk,
            "message": latest_notification.message,
        } if latest_notification else None,
    })


def _get_tracking_snapshot(journey, route_stages):
    """Build tracking values using the latest cached vehicle position."""
    trip = journey.trip
    vehicle_pos = None
    if trip.current_latitude is not None and trip.current_longitude is not None:
        vehicle_pos = (float(trip.current_latitude), float(trip.current_longitude))

    destination = journey.destination_stage
    stages_to_destination = [
        stage for stage in route_stages
        if stage.sequence_order <= destination.sequence_order
    ]
    current_stage = None
    for stage in stages_to_destination:
        if vehicle_pos and is_near_stage(vehicle_pos[0], vehicle_pos[1], stage):
            current_stage = stage

    if current_stage:
        next_stage = next(
            (stage for stage in stages_to_destination
             if stage.sequence_order > current_stage.sequence_order),
            None,
        )
    else:
        next_stage = stages_to_destination[0] if stages_to_destination else None

    remaining = calculate_remaining(vehicle_pos, next_stage, destination) if vehicle_pos and next_stage else None
    return {
        "current_stage": current_stage,
        "next_stage": next_stage,
        "remaining": remaining,
        "progress_percent": _get_progress_percent(stages_to_destination, current_stage),
    }


def _get_progress_percent(stages, current_stage):
    """Estimate journey progress by completed route stages, clamped to 0–100."""
    if not stages or not current_stage:
        return 0
    if len(stages) == 1:
        return 100

    stage_positions = {stage.id: index for index, stage in enumerate(stages)}
    current_index = stage_positions.get(current_stage.id, 0)
    return round(current_index / (len(stages) - 1) * 100)


def _latest_journey_notification(journey):
    return Notification.objects.filter(
        recipient_type=Notification.RecipientType.PASSENGER,
        recipient_id=journey.passenger_id,
        journey=journey,
    ).order_by("-timestamp", "-pk").first()


@login_required
def end_journey(request, journey_id):
    journey = get_object_or_404(JourneySession, pk=journey_id, passenger=request.user)
    
    if request.method == "POST":
        end_journey(journey)
        return redirect("core:dashboard")
    
    return render(request, "journeys/confirm_end.html", {"journey": journey})


@login_required
def history(request):
    journeys = JourneySession.objects.filter(
        passenger=request.user,
        status=JourneySession.Status.ENDED
    ).order_by("-end_time")
    return render(request, "journeys/history.html", {"journeys": journeys})