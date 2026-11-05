"""WebSocket URL routing for trip location updates."""

from django.urls import re_path
from .consumers import TripLocationConsumer

websocket_urlpatterns = [
    re_path(r'ws/trips/(?P<trip_id>\d+)/$', TripLocationConsumer.as_asgi()),
]
