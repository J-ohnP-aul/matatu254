from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from fleet.models import Matatu
from journeys.models import JourneySession
from r_outes.models import Route, Stage
from trips.models import ActiveTrip

User = get_user_model()


class ConductorAuthorizationTests(TestCase):
    def test_conductor_assigned_to_matatu_can_view_trip_detail(self):
        matatu = Matatu.objects.create(
            registration_number="KAA 101A",
            operator="City Shuttle",
        )
        conductor = User.objects.create_user(
            username="conductor1",
            password="secret123",
            role=User.CONDUCTOR,
        )
        conductor.matatu = matatu
        conductor.save()

        route = Route.objects.create(name="Westlands Route")
        Stage.objects.create(
            route=route,
            name="Westlands",
            sequence_order=1,
            latitude=-1.2833,
            longitude=36.8167,
        )
        trip = ActiveTrip.objects.create(
            matatu=matatu,
            route=route,
            status=ActiveTrip.Status.ACTIVE,
        )

        self.client.login(username="conductor1", password="secret123")
        response = self.client.get(reverse("conductor:trip-detail", args=[trip.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Not Authorized")
        self.assertContains(response, "Live trip")
        self.assertContains(response, "Alighting per stage")

    @patch("conductor.views.remaining_road_distance")
    def test_tracking_endpoint_recalculates_distance_from_latest_position(self, remaining_distance_mock):
        matatu = Matatu.objects.create(
            registration_number="KDA 1442",
            operator="City Shuttle",
        )
        conductor = User.objects.create_user(
            username="tracking-conductor",
            password="secret123",
            role=User.CONDUCTOR,
            matatu=matatu,
        )
        route = Route.objects.create(name="Kisii - Migori")
        Stage.objects.create(
            route=route,
            name="Kisii New Bus Station",
            sequence_order=1,
            latitude=-0.68,
            longitude=34.77,
        )
        Stage.objects.create(
            route=route,
            name="Migori",
            sequence_order=2,
            latitude=-1.06,
            longitude=34.47,
        )
        trip = ActiveTrip.objects.create(
            matatu=matatu,
            route=route,
            status=ActiveTrip.Status.ACTIVE,
            current_latitude=-0.68,
            current_longitude=34.77,
        )
        passenger = User.objects.create_user(
            username="trip-passenger",
            password="secret123",
            role=User.PASSANGER,
        )
        destination = route.stages.get(sequence_order=2)
        JourneySession.objects.create(
            passenger=passenger,
            trip=trip,
            destination_stage=destination,
            status=JourneySession.Status.IN_TRANSIT,
        )
        remaining_distance_mock.side_effect = lambda position, *_: SimpleNamespace(
            distance_m=20000 if position[1] == 34.77 else 15000,
            distance_km=20 if position[1] == 34.77 else 15,
            duration_s=1800,
            duration_minutes=30,
        )
        self.client.force_login(conductor)
        url = reverse("conductor:trip-tracking-data", args=[trip.pk])

        first_response = self.client.get(url)
        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(first_response.json()["distance_m"], 20000)
        self.assertEqual(first_response.json()["next_stage"], "Migori")
        self.assertEqual(first_response.json()["total_passengers"], 1)
        self.assertEqual(first_response.json()["alighting_counts"]["2"], 1)
        self.assertTrue(first_response.json()["gps_stale"])
        self.assertIsNone(first_response.json()["gps_age_seconds"])

        trip.current_longitude = 34.78
        trip.last_ping_at = timezone.now()
        trip.save(update_fields=["current_longitude", "last_ping_at"])
        second_response = self.client.get(url)

        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_response.json()["distance_m"], 15000)
        self.assertFalse(second_response.json()["gps_stale"])
        self.assertLessEqual(second_response.json()["gps_age_seconds"], 60)
        self.assertEqual(remaining_distance_mock.call_count, 4)

    def test_tracking_endpoint_marks_old_gps_ping_stale(self):
        matatu = Matatu.objects.create(
            registration_number="KDB 1453",
            operator="City Shuttle",
        )
        conductor = User.objects.create_user(
            username="stale-tracking-conductor",
            password="secret123",
            role=User.CONDUCTOR,
            matatu=matatu,
        )
        route = Route.objects.create(name="Stale GPS Route")
        Stage.objects.create(
            route=route,
            name="Start",
            sequence_order=1,
            latitude=-0.68,
            longitude=34.77,
        )
        trip = ActiveTrip.objects.create(
            matatu=matatu,
            route=route,
            status=ActiveTrip.Status.ACTIVE,
            last_ping_at=timezone.now() - timedelta(seconds=120),
        )
        self.client.force_login(conductor)

        response = self.client.get(reverse("conductor:trip-tracking-data", args=[trip.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["gps_stale"])
        self.assertGreaterEqual(response.json()["gps_age_seconds"], 120)
