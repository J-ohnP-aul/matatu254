from django.urls import path
from . import views

app_name = "conductor"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("trip/<int:trip_id>/", views.trip_detail, name="trip-detail"),
    path("trip/<int:trip_id>/tracking-data/", views.trip_tracking_data, name="trip-tracking-data"),
    path("trip/<int:trip_id>/route-data/", views.trip_route_data, name="trip-route-data"),
    path("trip/<int:trip_id>/passengers/", views.trip_passengers, name="trip-passengers"),
    path("notifications/", views.notifications, name="notifications"),
]