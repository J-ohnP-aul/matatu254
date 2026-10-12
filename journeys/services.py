"""
journeys/services.py

Business logic for passenger journey sessions.
"""
from django.utils import timezone
from django.db import transaction

from journeys.models import JourneySession
from notifications.models import Notification
from r_outes.routes_services import is_near_stage, remaining_road_distance


def get_active_journey(passenger):
    """Return the passenger's latest journey that has not been ended."""
    active_statuses = [
        JourneySession.Status.DESTINATION_SELECTED,
        JourneySession.Status.IN_TRANSIT,
        JourneySession.Status.APPROACHING,
        JourneySession.Status.ARRIVED,
    ]
    return (
        JourneySession.objects
        .filter(passenger=passenger, status__in=active_statuses)
        .select_related("trip", "trip__route", "trip__matatu", "destination_stage")
        .order_by("-start_time")
        .first()
    )


def create_journey_session(passenger, trip, destination_stage) -> JourneySession:
    """Create a new journey session for a passenger on a trip."""
    return JourneySession.objects.create(
        passenger=passenger,
        trip=trip,
        destination_stage=destination_stage,
        status=JourneySession.Status.DESTINATION_SELECTED,
    )


def calculate_remaining(vehicle_pos, next_stage, destination_stage):
    """Calculate remaining distance and ETA to destination."""
    if not vehicle_pos or not next_stage:
        return None
    return remaining_road_distance(vehicle_pos, next_stage, destination_stage)


def update_journey_status(journey: JourneySession) -> JourneySession:
    """
    Determine and update journey status based on vehicle position.
    Returns the journey (potentially with updated status).
    """
    trip = journey.trip
    route_stages = list(trip.route.stages.order_by("sequence_order"))
    
    # Vehicle position from trip cache
    vehicle_pos = None
    if trip.current_latitude is not None and trip.current_longitude is not None:
        vehicle_pos = (float(trip.current_latitude), float(trip.current_longitude))
    
    if not vehicle_pos:
        return journey
    
    # Find current stage (last reached) and next stage (first not reached)
    current_stage = None
    next_stage = None

    destination_order = journey.destination_stage.sequence_order
    route_stages = [stage for stage in route_stages if stage.sequence_order <= destination_order]
    for stage in route_stages:
        if is_near_stage(vehicle_pos[0], vehicle_pos[1], stage):
            current_stage = stage
        elif next_stage is None:
            next_stage = stage

    if current_stage and current_stage.id != journey.destination_stage_id:
        _send_stage_reached_notification(journey, current_stage)
    
    # Determine new status based on current status and position
    new_status = journey.status
    
    if journey.status == JourneySession.Status.DESTINATION_SELECTED:
        if current_stage is not None:
            new_status = JourneySession.Status.IN_TRANSIT
    
    elif journey.status == JourneySession.Status.IN_TRANSIT:
        if current_stage and current_stage.id == journey.destination_stage_id:
            new_status = JourneySession.Status.APPROACHING
        elif next_stage and next_stage.id == journey.destination_stage_id:
            if is_near_stage(vehicle_pos[0], vehicle_pos[1], journey.destination_stage):
                new_status = JourneySession.Status.APPROACHING
    
    elif journey.status == JourneySession.Status.APPROACHING:
        if current_stage and current_stage.id == journey.destination_stage_id:
            new_status = JourneySession.Status.ARRIVED
    
    # Update if changed
    if new_status != journey.status:
        journey.status = new_status
        journey.save(update_fields=["status"])
        
        # Trigger notification on APPROACHING
        if new_status == JourneySession.Status.APPROACHING:
            _send_approaching_notification(journey)
        elif new_status == JourneySession.Status.ARRIVED:
            _send_arrived_notification(journey)
    
    return journey


def _send_stage_reached_notification(journey: JourneySession, stage):
    """Create one in-app event when the vehicle reaches an intermediate stop."""
    message = f"Reached {stage.name}"
    exists = Notification.objects.filter(
        recipient_type=Notification.RecipientType.PASSENGER,
        recipient_id=journey.passenger_id,
        journey=journey,
        message=message,
    ).exists()
    if not exists:
        Notification.objects.create(
            recipient_type=Notification.RecipientType.PASSENGER,
            recipient_id=journey.passenger_id,
            journey=journey,
            message=message,
        )


def _send_approaching_notification(journey: JourneySession):
    """Send approaching notification to passenger and assigned conductor."""
    passenger_message = f"Approaching {journey.destination_stage.name} — prepare to alight"
    Notification.objects.create(
        recipient_type=Notification.RecipientType.PASSENGER,
        recipient_id=journey.passenger_id,
        journey=journey,
        message=passenger_message,
    )

    matatu = journey.trip.matatu
    for conductor in matatu.conductor.all():
        Notification.objects.create(
            recipient_type=Notification.RecipientType.CONDUCTOR,
            recipient_id=conductor.pk,
            journey=journey,
            message=f"{matatu.registration_number} is approaching {journey.destination_stage.name}",
        )


def _send_arrived_notification(journey: JourneySession):
    """Notify passenger and assigned conductor once the destination is reached."""
    passenger_message = f"You have arrived at your destination: {journey.destination_stage.name}"
    if not Notification.objects.filter(
        recipient_type=Notification.RecipientType.PASSENGER,
        recipient_id=journey.passenger_id,
        journey=journey,
        message=passenger_message,
    ).exists():
        Notification.objects.create(
            recipient_type=Notification.RecipientType.PASSENGER,
            recipient_id=journey.passenger_id,
            journey=journey,
            message=passenger_message,
        )

    matatu = journey.trip.matatu
    for conductor in matatu.conductor.all():
        conductor_message = f"Passenger has arrived at {journey.destination_stage.name}"
        if not Notification.objects.filter(
            recipient_type=Notification.RecipientType.CONDUCTOR,
            recipient_id=conductor.pk,
            journey=journey,
            message=conductor_message,
        ).exists():
            Notification.objects.create(
                recipient_type=Notification.RecipientType.CONDUCTOR,
                recipient_id=conductor.pk,
                journey=journey,
                message=conductor_message,
            )


@transaction.atomic
def end_journey(journey: JourneySession) -> JourneySession:
    """Mark journey as ended."""
    journey.status = JourneySession.Status.ENDED
    journey.end_time = timezone.now()
    journey.save(update_fields=["status", "end_time"])
    return journey