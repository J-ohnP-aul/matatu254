from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from journeys.services import get_active_journey
from journeys.models import JourneySession


def home(request):
  active_journey = None
  if request.user.is_authenticated:
    if request.user.role == 'PASSANGER':
      active_journey = get_active_journey(request.user)
  return render(request, 'core/home.html', {'active_journey': active_journey})


def offline(request):
  return render(request, 'offline.html')

@login_required
def dashboard(request):
  context = {}
  if request.user.role == 'PASSANGER':
    context['active_journey'] = get_active_journey(request.user)
    context['recent_journeys'] = JourneySession.objects.filter(
      passenger=request.user, status=JourneySession.Status.ENDED
    ).select_related(
      'trip__route', 'trip__matatu', 'destination_stage'
    ).order_by('-start_time')[:3]
  return render(request, "core/dashboard.html", context)
