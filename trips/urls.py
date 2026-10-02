from django.urls import path
from . import views
urlpatterns = [
  path("trips/<int:trip_id>/ping/", views.ping, name="trip-ping"),
]