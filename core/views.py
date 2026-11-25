from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from journeys.services import get_active_journey
from journeys.models import JourneySession
from r_outes.models import Route


def home(request):
  active_journey = None
  home_routes = []
  if request.user.is_authenticated and request.user.role == 'PASSANGER':
    active_journey = get_active_journey(request.user)
    home_routes = (
      Route.objects.annotate(stage_total=Count('stages'))
      .order_by('name')[:6]
    )
  return render(request, 'core/home.html', {
    'active_journey': active_journey,
    'home_routes': home_routes,
  })


def offline(request):
  return render(request, 'offline.html')

@login_required
def dashboard(request):
  if request.user.role == 'CONDUCTOR':
    return redirect('conductor:dashboard')

  context = {}
  if request.user.role == 'PASSANGER':
    context['active_journey'] = get_active_journey(request.user)
    context['recent_journeys'] = JourneySession.objects.filter(
      passenger=request.user, status=JourneySession.Status.ENDED
    ).select_related(
      'trip__route', 'trip__matatu', 'destination_stage'
    ).order_by('-start_time')[:3]
  return render(request, "core/dashboard.html", context)
