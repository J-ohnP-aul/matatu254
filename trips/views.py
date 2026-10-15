from django.shortcuts import render
from django.db.models import Q

import json
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.shortcuts import get_object_or_404

from .models import ActiveTrip
from .services import record_ping

# Create your views here.

@csrf_exempt
@require_POST
def ping(request, trip_id):
  trip = get_object_or_404(
    ActiveTrip, 
    pk=trip_id, 
    status=ActiveTrip.Status.ACTIVE
  )
  # Allow ping from either matatu owner or assigned conductor via either direct or reverse assignment
  user_matatu = getattr(request.user, 'matatu', None)
  is_assigned = (
      user_matatu == trip.matatu
      or trip.matatu.owner == request.user
      or trip.matatu.conductor.filter(pk=request.user.pk).exists()
  )
  if not is_assigned:
    return JsonResponse({"error": "Not authorized for this trip"}, status=403)
  
  try:
    data = json.loads(request.body)
    latitude = data["latitude"]
    longitude = data["longitude"]
  except (json.JSONDecodeError, KeyError, TypeError):
    return JsonResponse({"error": "A valid latitude and longitude are required"}, status=400)

  try:
    record_ping(
      trip=trip,
      latitude=latitude,
      longitude=longitude,
      recorded_at=data.get("recorded_at"),
    )
  except ValueError as exc:
    return JsonResponse({"error": str(exc)}, status=400)
  return JsonResponse({"ok": True})


@require_GET
def location_stream(request, trip_id):
    """Server-Sent Events stream for real-time location updates."""
    trip = get_object_or_404(ActiveTrip, pk=trip_id, status=ActiveTrip.Status.ACTIVE)
    
    # Check authorization (same as ping)
    user_matatu = getattr(request.user, 'matatu', None)
    is_assigned = (
        user_matatu == trip.matatu
        or trip.matatu.owner == request.user
        or trip.matatu.conductor.filter(pk=request.user.pk).exists()
    )
    if not is_assigned:
        return JsonResponse({"error": "Not authorized for this trip"}, status=403)
    
    def event_stream():
        import time
        last_ping_time = None
        while True:
            trip.refresh_from_db()
            if trip.last_ping_at and trip.last_ping_at != last_ping_time:
                last_ping_time = trip.last_ping_at
                data = {
                    "type": "ping",
                    "latitude": float(trip.current_latitude) if trip.current_latitude else None,
                    "longitude": float(trip.current_longitude) if trip.current_longitude else None,
                    "timestamp": trip.last_ping_at.isoformat(),
                }
                yield f"data: {json.dumps(data)}\n\n"
            time.sleep(1)
    
    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


@require_GET
def latest_position(request, trip_id):
    """Return the latest known position for a trip."""
    trip = get_object_or_404(ActiveTrip, pk=trip_id, status=ActiveTrip.Status.ACTIVE)
    
    if trip.current_latitude is None or trip.current_longitude is None:
        return JsonResponse({"error": "No position available"}, status=404)

    latitude = float(trip.current_latitude)
    longitude = float(trip.current_longitude)
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return JsonResponse({"error": "No valid position available"}, status=404)
    
    return JsonResponse({
        "latitude": latitude,
        "longitude": longitude,
        "timestamp": trip.last_ping_at.isoformat() if trip.last_ping_at else None,
        "gps_age_seconds": trip.gps_age_seconds,
        "is_stale": trip.is_stale,
    })
