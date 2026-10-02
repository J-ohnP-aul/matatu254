from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from trips.models import ActiveTrip

# Create your views here.
def home(request):
  trip = ActiveTrip.objects.filter(
    status=ActiveTrip.Status.ACTIVE
  ).order_by("-start_time").first()
  return render(request, 'core/home.html', {'trip':trip})

@login_required
def dashboard(request):
  return render(request, "core/dashboard.html")
