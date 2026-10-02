from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from trips.models import ActiveTrip
from tracking.models import TripLocationLog


@transaction.atomic
def record_ping(trip: ActiveTrip, latitude, longitude, recorded_at=None):
  """Persist a ping and refresh the trip's current position cache."""
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
    
    
    
#     trip = ActiveTrip.objects.get(pk=trip_id)

# if trip.is_stale:
#   # Signal lost. Show "last known position, Ns ago" — don't pretend it's live.
#   position = None
# else:
#   position = (trip.current_latitude, trip.current_longitude)