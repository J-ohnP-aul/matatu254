from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from trips.models import ActiveTrip
from django.db.models import Q


def home(request):
  trip = None
  if request.user.is_authenticated:
    trip = ActiveTrip.objects.filter(
      status=ActiveTrip.Status.ACTIVE
    ).filter(
      Q(matatu__owner=request.user) | Q(matatu__conductor=request.user)
    ).order_by("-start_time").first()
  return render(request, 'core/home.html', {'trip':trip})

@login_required
def dashboard(request):
  return render(request, "core/dashboard.html")
