from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from journeys.services import get_active_journey


def home(request):
  active_journey = None
  if request.user.is_authenticated:
    if request.user.role == 'PASSANGER':
      active_journey = get_active_journey(request.user)
  return render(request, 'core/home.html', {'active_journey': active_journey})

@login_required
def dashboard(request):
  if request.user.role == 'PASSANGER':
    active_journey = get_active_journey(request.user)
    if active_journey:
        return redirect("journeys:journey-detail", journey_id=active_journey.pk)
  return render(request, "core/dashboard.html")
