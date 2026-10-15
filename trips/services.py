from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from trips.models import ActiveTrip
from tracking.models import TripLocationLog
import math


@transaction.atomic
def record_ping(trip: ActiveTrip, latitude, longitude, recorded_at=None):
  """Persist a ping and refresh the trip's current position cache."""
  try:
    latitude = float(latitude)
    longitude = float(longitude)
  except (TypeError, ValueError):
    raise ValueError("Latitude and longitude must be valid numbers")
  if (not math.isfinite(latitude) or not math.isfinite(longitude)
      or not -90 <= latitude <= 90 or not -180 <= longitude <= 180):
    raise ValueError("Latitude or longitude is outside the valid coordinate range")

  if isinstance(recorded_at, str):
    recorded_at = parse_datetime(recorded_at)
  recorded_at = recorded_at or timezone.now()

  TripLocationLog.objects.create(
    trip=trip,
    latitude=latitude,
    longitude=longitude,
    recorded_at=recorded_at,
  )

  # Only advance the cache if this ping is newer than what we have.
  # Prevents an out-of-order upload from rewinding the position.
  if trip.last_ping_at is None or recorded_at > trip.last_ping_at:
    trip.current_latitude = latitude
    trip.current_longitude = longitude
    trip.last_ping_at = recorded_at
    trip.save(update_fields=["current_latitude", "current_longitude", "last_ping_at"])

    # Stage events are driven by fresh GPS pings, not by whether a passenger
    # happens to have the journey page open at that moment.
    from journeys.models import JourneySession
    from journeys.services import update_journey_status

    active_statuses = [
      JourneySession.Status.DESTINATION_SELECTED,
      JourneySession.Status.IN_TRANSIT,
      JourneySession.Status.APPROACHING,
    ]
    journeys = JourneySession.objects.filter(
      trip=trip,
      status__in=active_statuses,
    ).select_related("passenger", "trip", "trip__matatu", "trip__route", "destination_stage")
    for journey in journeys:
      update_journey_status(journey)
#     trip = ActiveTrip.objects.get(pk=trip_id)

# if trip.is_stale:
#   # Signal lost. Show "last known position, Ns ago" — don't pretend it's live.
#   position = None
# else:
#   position = (trip.current_latitude, trip.current_longitude)
