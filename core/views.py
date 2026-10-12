from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from trips.models import ActiveTrip
from django.db.models import Q
from journeys.services import get_active_journey


def home(request):
  trip = None
  active_journey = None
  if request.user.is_authenticated:
    if request.user.role == 'PASSANGER':
      active_journey = get_active_journey(request.user)
    trip = ActiveTrip.objects.filter(
      status=ActiveTrip.Status.ACTIVE
    ).filter(
      Q(matatu__owner=request.user) | Q(matatu__conductor=request.user)
    ).order_by("-start_time").first()
  return render(request, 'core/home.html', {'trip':trip, 'active_journey': active_journey})

@login_required
def dashboard(request):
  if request.user.role == 'PASSANGER':
    active_journey = get_active_journey(request.user)
    if active_journey:
        return redirect("journeys:journey-detail", journey_id=active_journey.pk)
  return render(request, "core/dashboard.html")
