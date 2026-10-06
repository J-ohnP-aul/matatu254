from django.urls import path
from . import views

app_name = "management"
urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    # Matatu management
    path("matatus/", views.matatu_list, name="matatu-list"),
    path("matatus/create/", views.matatu_create, name="matatu-create"),
    path("matatus/<int:pk>/edit/", views.matatu_edit, name="matatu-edit"),
    path("matatus/<int:pk>/qr/", views.matatu_qr, name="matatu-qr"),
    # Route management
    path("routes/", views.route_list, name="route-list"),
    path("routes/create/", views.route_create, name="route-create"),
    path("routes/<int:pk>/edit/", views.route_edit, name="route-edit"),
    path("routes/<int:pk>/stages/", views.route_stages, name="route-stages"),
    path("routes/<int:pk>/stages/create/", views.stage_create, name="stage-create"),
    path("stages/<int:pk>/edit/", views.stage_edit, name="stage-edit"),
    path("stages/<int:pk>/delete/", views.stage_delete, name="stage-delete"),
    # Trip management
    path("trips/", views.trip_list, name="trip-list"),
    path("trips/create/", views.trip_create, name="trip-create"),
    path("trips/<int:pk>/start/", views.trip_start, name="trip-start"),
    path("trips/<int:pk>/end/", views.trip_end, name="trip-end"),
    path("trips/<int:pk>/cancel/", views.trip_cancel, name="trip-cancel"),
    # System config
    path("config/", views.system_config, name="system-config"),
    path("config/<int:pk>/edit/", views.system_config_edit, name="system-config-edit"),
]