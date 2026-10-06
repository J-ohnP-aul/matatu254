from django.urls import path
from . import views

app_name = "conductor"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("trip/<int:trip_id>/", views.trip_detail, name="trip-detail"),
    path("trip/<int:trip_id>/passengers/", views.trip_passengers, name="trip-passengers"),
    path("notifications/", views.notifications, name="notifications"),
]