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


def advance_journey_progress(journey: JourneySession, route_stages, vehicle_pos):
    """
    Monotonic stage completion from along-track distance.

    Projects the vehicle onto the ordered stage line and marks every stage
    whose cumulative distance is behind the vehicle as completed. State is
    persisted on the journey (completed_stage_ids / current_stage_index)
    and only ever advances: a vehicle parked between two stages keeps the
    last completed stage visible and never un-completes a passed one.

    Returns (current_stage, next_stage) for the journey's destination span.
    """
    from core.geo import haversine_distance_m
    from r_outes.routes_services import along_track_position

    dest_order = journey.destination_stage.sequence_order
    stages = [st for st in route_stages if st.sequence_order <= dest_order]
    if not stages:
        journey.completed_stage_ids = []
        journey.current_stage_index = 0
        return None, None

    perp = 0.0
    if vehicle_pos is not None:
        along, _total, perp = along_track_position(vehicle_pos[0], vehicle_pos[1], stages)
    else:
        along = 0.0

    cumulative = [0.0]
    for a, b in zip(stages, stages[1:]):
        cumulative.append(cumulative[-1] + haversine_distance_m(
            float(a.latitude), float(a.longitude),
            float(b.latitude), float(b.longitude),
        ))

    # 25 m tolerance: a fix just past a stage still counts it as completed.
    # The first stage additionally needs the vehicle to have actually
    # reached the corridor (perp <= 100 m or clear progress > tolerance) —
    # otherwise a passenger still walking to the route start would count
    # the first stage as passed (along clamps to 0 there).
    derived_ids = set()
    for i, c in enumerate(cumulative):
        if c > along + 25:
            break
        if i == 0 and perp > 100 and along <= 25:
            continue  # not yet at the route start
        derived_ids.add(stages[i].id)
    completed_ids = set(journey.completed_stage_ids or []) | derived_ids
    ordered = [st.id for st in stages if st.id in completed_ids]

    journey.completed_stage_ids = ordered
    if ordered:
        index = max(journey.current_stage_index, len(ordered) - 1)
        journey.current_stage_index = min(index, len(stages) - 1)
    else:
        journey.current_stage_index = 0

    if not ordered:
        # Journey not started yet: nothing completed, first stage upcoming.
        return None, stages[0]
    current_stage = stages[journey.current_stage_index]
    next_index = journey.current_stage_index + 1
    next_stage = stages[next_index] if next_index < len(stages) else None
    return current_stage, next_stage


def update_journey_status(journey: JourneySession) -> JourneySession:
    """
    Determine and update journey status based on vehicle position.

    Stage memory is monotonic (see advance_journey_progress): passed stages
    stay completed while the vehicle is in transit between checkpoints.
    """
    from r_outes.routes_services import is_near_stage

    trip = journey.trip
    route_stages = list(trip.route.stages.order_by("sequence_order"))

    vehicle_pos = None
    if trip.current_latitude is not None and trip.current_longitude is not None:
        vehicle_pos = (float(trip.current_latitude), float(trip.current_longitude))

    current_stage, next_stage = advance_journey_progress(journey, route_stages, vehicle_pos)

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
            if vehicle_pos and is_near_stage(vehicle_pos[0], vehicle_pos[1], journey.destination_stage):
                new_status = JourneySession.Status.APPROACHING

    elif journey.status == JourneySession.Status.APPROACHING:
        if vehicle_pos and current_stage and current_stage.id == journey.destination_stage_id:
            if is_near_stage(vehicle_pos[0], vehicle_pos[1], journey.destination_stage):
                new_status = JourneySession.Status.ARRIVED

    # Update if changed
    if new_status != journey.status:
        journey.status = new_status

        # Trigger notification on APPROACHING
        if new_status == JourneySession.Status.APPROACHING:
            _send_approaching_notification(journey)
        elif new_status == JourneySession.Status.ARRIVED:
            _send_arrived_notification(journey)

    journey.save(update_fields=["status", "completed_stage_ids", "current_stage_index"])
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
            send_push=False,
        )


def _send_approaching_notification(journey: JourneySession):
    """Send approaching notification to passenger and assigned conductor."""
    passenger_message = f"Approaching {journey.destination_stage.name} — prepare to alight"
    Notification.objects.create(
        recipient_type=Notification.RecipientType.PASSENGER,
        recipient_id=journey.passenger_id,
        journey=journey,
        message=passenger_message,
        send_push=False,
    )

    from trips.services import get_matatu_conductors
    matatu = journey.trip.matatu
    for conductor in get_matatu_conductors(matatu):
        Notification.objects.create(
            recipient_type=Notification.RecipientType.CONDUCTOR,
            recipient_id=conductor.pk,
            journey=journey,
            message=f"{matatu.registration_number} is approaching {journey.destination_stage.name}",
            send_push=False,
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
            send_push=True,
        )

    from trips.services import get_matatu_conductors
    matatu = journey.trip.matatu
    for conductor in get_matatu_conductors(matatu):
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
                send_push=True,
            )


@transaction.atomic
def end_journey(journey: JourneySession) -> JourneySession:
    """Mark journey as ended."""
    journey.status = JourneySession.Status.ENDED
    journey.end_time = timezone.now()
    journey.save(update_fields=["status", "end_time"])
    return journey