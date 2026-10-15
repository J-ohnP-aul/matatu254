from django.urls import path
from . import views
urlpatterns = [
  path("<int:trip_id>/ping/", views.ping, name="trip-ping"),
  path("<int:trip_id>/location-stream/", views.location_stream, name="location-stream"),
  path("<int:trip_id>/latest-position/", views.latest_position, name="latest-position"),
]