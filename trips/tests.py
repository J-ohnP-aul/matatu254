"""Tests for trip location tracking — HTTP ping, WebSocket, and transport config."""

import json
from datetime import timedelta
from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone


from fleet.models import Matatu
from journeys.models import JourneySession
from r_outes.models import Route, Stage
from tracking.models import TripLocationLog
from trips.models import ActiveTrip


User = get_user_model()


def _build_trip(conductor=None, owner=None):
    """Create a minimal active trip with a route and stages."""
    route = Route.objects.create(name="Test Route")
    Stage.objects.create(route=route, name="Start", sequence_order=1, latitude=0, longitude=0)
    Stage.objects.create(route=route, name="End", sequence_order=2, latitude=0, longitude=0.01)
    matatu = Matatu.objects.create(
        registration_number=f"KAA {Matatu.objects.count():03d}X",
        operator="Test",
        owner=owner,
    )
    trip = ActiveTrip.objects.create(matatu=matatu, route=route, status=ActiveTrip.Status.ACTIVE)
    if conductor:
        conductor.matatu = matatu
        conductor.save(update_fields=["matatu"])
    return trip


# ------------------------------------------------------------------ #
# HTTP ping regression tests
# ------------------------------------------------------------------ #


class HTTPPingTests(TestCase):
    """Verify the existing HTTP ping endpoint still works correctly."""

    def setUp(self):
        self.conductor = User.objects.create_user(username="conductor", password="pass", role=User.CONDUCTOR)
        self.trip = _build_trip(conductor=self.conductor)
        self.url = reverse("trip-ping", args=[self.trip.id])
        self.client.force_login(self.conductor)

    def test_ping_records_location(self):
        """A valid ping creates a TripLocationLog and updates the cache."""
        resp = self.client.post(
            self.url,
            data=json.dumps({"latitude": -1.28, "longitude": 36.82}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("ok"))
        self.assertEqual(TripLocationLog.objects.filter(trip=self.trip).count(), 1)
        self.trip.refresh_from_db()
        self.assertEqual(float(self.trip.current_latitude), -1.28)
        self.assertEqual(float(self.trip.current_longitude), 36.82)

    def test_invalid_coordinates_rejected(self):
        """Out-of-range coordinates return 400."""
        resp = self.client.post(
            self.url,
            data=json.dumps({"latitude": 999, "longitude": 36.82}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(TripLocationLog.objects.filter(trip=self.trip).count(), 0)

    def test_out_of_order_timestamp_does_not_rewind(self):
        """An older timestamp should not rewind the cached position."""
        now = timezone.now()
        # First ping at now
        self.client.post(
            self.url,
            data=json.dumps({"latitude": -1.28, "longitude": 36.82, "recorded_at": now.isoformat()}),
            content_type="application/json",
        )
        # Second ping with an older timestamp
        old = now - timedelta(seconds=60)
        self.client.post(
            self.url,
            data=json.dumps({"latitude": -1.30, "longitude": 36.84, "recorded_at": old.isoformat()}),
            content_type="application/json",
        )
        self.trip.refresh_from_db()
        # Position should still be from the first (newer) ping
        self.assertEqual(float(self.trip.current_latitude), -1.28)

    def test_unauthorized_user_cannot_ping(self):
        """A random user cannot ping a trip they are not assigned to."""
        other = User.objects.create_user(username="other", password="pass")
        self.client.force_login(other)
        resp = self.client.post(
            self.url,
            data=json.dumps({"latitude": -1.28, "longitude": 36.82}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_location_history_recorded(self):
        """Multiple pings create multiple TripLocationLog entries."""
        for lat in (-1.28, -1.29, -1.30):
            self.client.post(
                self.url,
                data=json.dumps({"latitude": lat, "longitude": 36.82}),
                content_type="application/json",
            )
        self.assertEqual(TripLocationLog.objects.filter(trip=self.trip).count(), 3)


class LatestPositionTests(TestCase):
    """Verify the latest-position endpoint still works."""

    def setUp(self):
        self.user = User.objects.create_user(username="viewer", password="pass")
        self.trip = _build_trip()
        self.trip.current_latitude = -1.28
        self.trip.current_longitude = 36.82
        self.trip.last_ping_at = timezone.now()
        self.trip.save(update_fields=["current_latitude", "current_longitude", "last_ping_at"])
        self.url = reverse("latest-position", args=[self.trip.id])

    def test_returns_position(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertAlmostEqual(data["latitude"], -1.28, places=2)
        self.assertFalse(data["is_stale"])

    def test_stale_position(self):
        self.trip.last_ping_at = timezone.now() - timedelta(seconds=120)
        self.trip.save(update_fields=["last_ping_at"])
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["is_stale"])


# ------------------------------------------------------------------ #
# WebSocket tests
# ------------------------------------------------------------------ #


class WebSocketAuthTests(TestCase):
    """WebSocket authorization mirrors HTTP view rules."""

    def setUp(self):
        self.conductor = User.objects.create_user(username="conductor", password="pass", role=User.CONDUCTOR)
        self.trip = _build_trip(conductor=self.conductor)
        self.passenger = User.objects.create_user(username="passenger", password="pass", role=User.PASSANGER)
        self.admin = User.objects.create_user(username="admin", password="pass", role=User.ADMIN)
        self.route = self.trip.route
        self.stage = Stage.objects.create(route=self.route, name="Dest", sequence_order=3, latitude=0, longitude=0.02)
        self.application = None

    def _get_application(self):
        if self.application is None:
            from config.asgi import application
            self.application = application
        return self.application

    def _ws_url(self):
        return f"/ws/trips/{self.trip.id}/"

    def test_anonymous_cannot_connect(self):
        """Anonymous users are rejected."""
        comm = WebsocketCommunicator(self._get_application(), self._ws_url())
        connected, _ = async_to_sync(comm.connect)()
        self.assertFalse(connected)

    def test_unauthorized_user_cannot_subscribe(self):
        """A user with no relation to the trip cannot connect."""
        random = User.objects.create_user(username="random", password="pass")
        comm = WebsocketCommunicator(self._get_application(), self._ws_url())
        comm.scope["user"] = random
        connected, _ = async_to_sync(comm.connect)()
        self.assertFalse(connected)

    def test_conductor_can_subscribe(self):
        """An assigned conductor can connect."""
        comm = WebsocketCommunicator(self._get_application(), self._ws_url())
        comm.scope["user"] = self.conductor
        connected, subprotocol = async_to_sync(comm.connect)()
        self.assertTrue(connected)
        async_to_sync(comm.disconnect)(code=1000)

    def test_passenger_with_journey_can_subscribe(self):
        """A passenger with an active journey session can connect."""
        JourneySession.objects.create(
            passenger=self.passenger,
            trip=self.trip,
            destination_stage=self.stage,
            status=JourneySession.Status.IN_TRANSIT,
        )
        comm = WebsocketCommunicator(self._get_application(), self._ws_url())
        comm.scope["user"] = self.passenger
        connected, _ = async_to_sync(comm.connect)()
        self.assertTrue(connected)
        async_to_sync(comm.disconnect)(code=1000)

    def test_admin_can_subscribe(self):
        """An admin can connect to any trip."""
        comm = WebsocketCommunicator(self._get_application(), self._ws_url())
        comm.scope["user"] = self.admin
        connected, _ = async_to_sync(comm.connect)()
        self.assertTrue(connected)
        async_to_sync(comm.disconnect)(code=1000)

    def test_passenger_without_journey_cannot_subscribe(self):
        """A passenger with no journey for this trip is rejected."""
        comm = WebsocketCommunicator(self._get_application(), self._ws_url())
        comm.scope["user"] = self.passenger
        connected, _ = async_to_sync(comm.connect)()
        self.assertFalse(connected)


class WebSocketLocationUpdateTests(TestCase):
    """WebSocket location.update uses the shared record_ping service."""

    def setUp(self):
        self.conductor = User.objects.create_user(username="conductor", password="pass", role=User.CONDUCTOR)
        self.trip = _build_trip(conductor=self.conductor)
        self.route = self.trip.route
        self.stage = Stage.objects.create(route=self.route, name="Dest", sequence_order=3, latitude=0, longitude=0.02)
        self.passenger = User.objects.create_user(username="passenger", password="pass", role=User.PASSANGER)
        JourneySession.objects.create(
            passenger=self.passenger,
            trip=self.trip,
            destination_stage=self.stage,
            status=JourneySession.Status.IN_TRANSIT,
        )
        self.application = None

    def _get_application(self):
        if self.application is None:
            from config.asgi import application
            self.application = application
        return self.application

    def _ws_url(self):
        return f"/ws/trips/{self.trip.id}/"

    def test_conductor_can_publish_location(self):
        """A conductor sends location.update → location.accepted is broadcast."""
        comm = WebsocketCommunicator(self._get_application(), self._ws_url())
        comm.scope["user"] = self.conductor
        connected, _ = async_to_sync(comm.connect)()
        self.assertTrue(connected)

        # Send location update
        async_to_sync(comm.send_json_to)({
            "type": "location.update",
            "trip_id": self.trip.id,
            "latitude": -1.28,
            "longitude": 36.82,
        })
        _, response = async_to_sync(comm.receive_from)()
        self.assertEqual(response["type"], "location.accepted")
        self.assertAlmostEqual(response["latitude"], -1.28, places=2)

        # Verify TripLocationLog was created
        self.assertEqual(TripLocationLog.objects.filter(trip=self.trip).count(), 1)
        async_to_sync(comm.disconnect)(code=1000)

    def test_invalid_coordinates_rejected_over_websocket(self):
        """Invalid coords return location.rejected, not broadcast."""
        comm = WebsocketCommunicator(self._get_application(), self._ws_url())
        comm.scope["user"] = self.conductor
        connected, _ = async_to_sync(comm.connect)()
        self.assertTrue(connected)

        async_to_sync(comm.send_json_to)({
            "type": "location.update",
            "trip_id": self.trip.id,
            "latitude": 999,
            "longitude": 36.82,
        })
        _, response = async_to_sync(comm.receive_from)()
        self.assertEqual(response["type"], "location.rejected")
        self.assertEqual(TripLocationLog.objects.filter(trip=self.trip).count(), 0)
        async_to_sync(comm.disconnect)(code=1000)

    def test_unauthorized_cannot_publish(self):
        """A passenger cannot send location.update."""
        comm = WebsocketCommunicator(self._get_application(), self._ws_url())
        comm.scope["user"] = self.passenger
        connected, _ = async_to_sync(comm.connect)()
        self.assertTrue(connected)

        async_to_sync(comm.send_json_to)({
            "type": "location.update",
            "trip_id": self.trip.id,
            "latitude": -1.28,
            "longitude": 36.82,
        })
        _, response = async_to_sync(comm.receive_from)()
        self.assertEqual(response["type"], "location.rejected")
        async_to_sync(comm.disconnect)(code=1000)

    def test_accepted_broadcast_to_group(self):
        """When conductor publishes, a passenger subscriber receives the update."""
        # Conductor publishes
        comm1 = WebsocketCommunicator(self._get_application(), self._ws_url())
        comm1.scope["user"] = self.conductor
        connected, _ = async_to_sync(comm1.connect)()
        self.assertTrue(connected)

        # Passenger subscribes
        comm2 = WebsocketCommunicator(self._get_application(), self._ws_url())
        comm2.scope["user"] = self.passenger
        connected, _ = async_to_sync(comm2.connect)()
        self.assertTrue(connected)

        # Conductor sends update
        async_to_sync(comm1.send_json_to)({
            "type": "location.update",
            "trip_id": self.trip.id,
            "latitude": -1.28,
            "longitude": 36.82,
        })

        # Conductor receives ack
        _, ack = async_to_sync(comm1.receive_from)()
        self.assertEqual(ack["type"], "location.accepted")

        # Passenger receives broadcast
        _, broadcast = async_to_sync(comm2.receive_from)()
        self.assertEqual(broadcast["type"], "location.accepted")
        self.assertAlmostEqual(broadcast["latitude"], -1.28, places=2)

        async_to_sync(comm1.disconnect)(code=1000)
        async_to_sync(comm2.disconnect)(code=1000)

    def test_stale_status_preserved(self):
        """Stale GPS status is correct over WebSocket."""
        comm = WebsocketCommunicator(self._get_application(), self._ws_url())
        comm.scope["user"] = self.conductor
        connected, _ = async_to_sync(comm.connect)()
        self.assertTrue(connected)

        # Send a ping with an old timestamp
        old = timezone.now() - timedelta(seconds=120)
        async_to_sync(comm.send_json_to)({
            "type": "location.update",
            "trip_id": self.trip.id,
            "latitude": -1.28,
            "longitude": 36.82,
            "recorded_at": old.isoformat(),
        })
        _, response = async_to_sync(comm.receive_from)()
        self.assertEqual(response["type"], "location.accepted")
        # The position is stale because the timestamp is old
        self.assertTrue(response["is_stale"])
        async_to_sync(comm.disconnect)(code=1000)


# ------------------------------------------------------------------ #
# Transport configuration tests
# ------------------------------------------------------------------ #


class TransportConfigTests(TestCase):
    """Verify LOCATION_TRANSPORT setting defaults and overrides."""

    @override_settings(LOCATION_TRANSPORT="polling")
    def test_default_is_polling(self):
        from django.conf import settings
        self.assertEqual(settings.LOCATION_TRANSPORT, "polling")

    @override_settings(LOCATION_TRANSPORT="websocket")
    def test_websocket_mode(self):
        from django.conf import settings
        self.assertEqual(settings.LOCATION_TRANSPORT, "websocket")

    @override_settings(LOCATION_TRANSPORT="auto")
    def test_auto_mode(self):
        from django.conf import settings
        self.assertEqual(settings.LOCATION_TRANSPORT, "auto")

    def test_journey_detail_exposes_transport(self):
        """journey_detail view passes location_transport to template."""
        passenger = User.objects.create_user(username="passenger", password="pass")
        trip = _build_trip()
        route = trip.route
        stage = Stage.objects.create(route=route, name="Dest", sequence_order=3, latitude=0, longitude=0.02)
        journey = JourneySession.objects.create(
            passenger=passenger,
            trip=trip,
            destination_stage=stage,
            status=JourneySession.Status.IN_TRANSIT,
        )
        self.client.force_login(passenger)
        url = reverse("journeys:journey-detail", args=[journey.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "data-location-transport")
