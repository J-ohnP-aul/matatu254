from django.urls import path
from . import views
urlpatterns = [
  path("<int:trip_id>/ping/", views.ping, name="trip-ping"),
  path("<int:trip_id>/latest-position/", views.latest_position, name="latest-position"),
  path("live/", views.live_vehicles, name="live-vehicles"),
]