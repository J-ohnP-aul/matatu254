from django.shortcuts import render
from django.db.models import Q


import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
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
  # Allow ping from either matatu owner or assigned conductor
  if not (trip.matatu.owner == request.user or getattr(request.user, 'matatu', None) == trip.matatu):
    return JsonResponse({"error": "Not authorized for this trip"}, status=403)
  
  data = json.loads(request.body)

  record_ping(
    trip=trip,
    latitude=data["latitude"],
    longitude=data["longitude"],
    recorded_at=data.get("recorded_at"),
  )
  return JsonResponse({"ok": True})
