from django.urls import path
from . import views

app_name = "journeys"
urlpatterns = [
    path("scan/", views.scan_qr, name="scan-qr"),
    path("scan/result/", views.scan_result, name="scan-result"),
    path("trip/<int:trip_id>/stages/", views.trip_stages, name="trip-stages"),
]