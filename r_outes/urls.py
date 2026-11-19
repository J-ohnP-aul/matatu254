from django.urls import path

from . import views

app_name = "explore"

urlpatterns = [
    path("map/", views.live_map, name="live-map"),
    path("explore/", views.explore, name="index"),
    path("explore/route/<int:pk>/", views.route_detail, name="route-detail"),
]
