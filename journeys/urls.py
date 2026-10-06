from django.urls import path
from . import views

app_name = "journeys"
urlpatterns = [
    path("scan/", views.scan_qr, name="scan-qr"),
    path("scan/result/", views.scan_result, name="scan-result"),
    path("trip/<int:trip_id>/stages/", views.trip_stages, name="trip-stages"),
    path("trip/<int:trip_id>/select/", views.select_destination, name="select-destination"),
    path("session/<int:journey_id>/", views.journey_detail, name="journey-detail"),
    path("session/<int:journey_id>/end/", views.end_journey, name="end-journey"),
    path("history/", views.history, name="history"),
]