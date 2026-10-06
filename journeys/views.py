from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from fleet.models import QRCode
from trips.models import ActiveTrip
from r_outes.models import Stage
from journeys.models import JourneySession
from journeys.services import (
    create_journey_session,
    update_journey_status,
    calculate_remaining,
    end_journey,
)


def scan_qr(request):
    """Render the camera scanner page"""
    return render(request, "journeys/scan.html")


def scan_result(request):
    """Process scanned QR code_value"""
    if request.method != "POST":
        return redirect("journeys:scan-qr")

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
    
    # Vehicle position
    vehicle_pos = None
    if trip.current_latitude and trip.current_longitude:
        vehicle_pos = (float(trip.current_latitude), float(trip.current_longitude))
    
    # Find current and next stage
    current_stage = None
    next_stage = None
    for stage in route_stages:
        if vehicle_pos and is_near_stage(vehicle_pos[0], vehicle_pos[1], stage):
            current_stage = stage
        elif next_stage is None:
            next_stage = stage
    
    # Remaining distance/ETA
    remaining = calculate_remaining(vehicle_pos, next_stage, journey.destination_stage) if vehicle_pos else None
    
    return render(request, "journeys/tracking.html", {
        "journey": journey,
        "trip": trip,
        "current_stage": current_stage,
        "next_stage": next_stage,
        "destination": journey.destination_stage,
        "remaining": remaining,
        "route_stages": route_stages,
    })


@login_required
def end_journey(request, journey_id):
    journey = get_object_or_404(JourneySession, pk=journey_id, passenger=request.user)
    
    if request.method == "POST":
        end_journey(journey)
        return redirect("journeys:history")
    
    return render(request, "journeys/confirm_end.html", {"journey": journey})


@login_required
def history(request):
    journeys = JourneySession.objects.filter(
        passenger=request.user,
        status=JourneySession.Status.ENDED
    ).order_by("-end_time")
    return render(request, "journeys/history.html", {"journeys": journeys})


# Need to import is_near_stage for the view
from r_outes.routes_services import is_near_stage