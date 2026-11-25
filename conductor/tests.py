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


class ConductorWorkspaceTests(TestCase):
    def setUp(self):
        self.matatu = Matatu.objects.create(
            registration_number="KCB 254A",
            operator="City Shuttle",
        )
        self.conductor = User.objects.create_user(
            username="workspace-conductor",
            password="Secure-Travel-92!",
            role=User.CONDUCTOR,
            matatu=self.matatu,
        )
        self.route = Route.objects.create(name="Nairobi Central Route")
        self.first_stage = Stage.objects.create(
            route=self.route,
            name="Central Station",
            sequence_order=1,
            latitude=-1.2833,
            longitude=36.8167,
        )
        self.last_stage = Stage.objects.create(
            route=self.route,
            name="Westlands",
            sequence_order=2,
            latitude=-1.2676,
            longitude=36.8108,
        )
        self.trip = ActiveTrip.objects.create(
            matatu=self.matatu,
            route=self.route,
            status=ActiveTrip.Status.ACTIVE,
        )

    def test_generic_post_login_dashboard_redirects_conductor_to_shift_overview(self):
        self.client.force_login(self.conductor)

        response = self.client.get(reverse("core:dashboard"))

        self.assertRedirects(response, reverse("conductor:dashboard"))

    def test_shift_overview_shows_trip_summary_and_destination_stage_totals(self):
        passenger = User.objects.create_user(
            username="central-bound",
            password="Secure-Travel-92!",
            role=User.PASSANGER,
        )
        JourneySession.objects.create(
            passenger=passenger,
            trip=self.trip,
            destination_stage=self.last_stage,
            status=JourneySession.Status.IN_TRANSIT,
        )
        self.client.force_login(self.conductor)

        response = self.client.get(reverse("conductor:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your shift")
        self.assertContains(response, "Nairobi Central Route")
        self.assertContains(response, "Passengers by destination")
        self.assertContains(response, "Manage passengers")
        self.assertContains(response, "Central Station")
        self.assertContains(response, "Westlands")

    def test_passenger_page_groups_active_journeys_and_excludes_ended_ones(self):
        active_passenger = User.objects.create_user(
            username="active-rider",
            password="Secure-Travel-92!",
            role=User.PASSANGER,
        )
        ended_passenger = User.objects.create_user(
            username="finished-rider",
            password="Secure-Travel-92!",
            role=User.PASSANGER,
        )
        JourneySession.objects.create(
            passenger=active_passenger,
            trip=self.trip,
            destination_stage=self.last_stage,
            status=JourneySession.Status.APPROACHING,
        )
        JourneySession.objects.create(
            passenger=ended_passenger,
            trip=self.trip,
            destination_stage=self.first_stage,
            status=JourneySession.Status.ENDED,
        )
        self.client.force_login(self.conductor)

        response = self.client.get(reverse("conductor:passengers"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Passengers by destination")
        self.assertContains(response, "Westlands")
        self.assertContains(response, "active-rider")
        self.assertNotContains(response, "finished-rider")

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


class TripSnapshotAlongTrackTests(TestCase):
    """The crew snapshot must work with a vehicle position set (it 500'd
    with NameError when the along-track path first ran)."""

    def test_snapshot_with_vehicle_position(self):
        from conductor.views import _get_trip_tracking_snapshot
        from r_outes.models import Route, Stage
        from trips.models import ActiveTrip
        from fleet.models import Matatu

        route = Route.objects.create(name='Crew route')
        s1 = Stage.objects.create(route=route, name='C1', sequence_order=1, latitude=-1.29, longitude=36.82)
        s2 = Stage.objects.create(route=route, name='C2', sequence_order=2, latitude=-1.30, longitude=36.82)
        s3 = Stage.objects.create(route=route, name='C3', sequence_order=3, latitude=-1.31, longitude=36.82)
        matatu = Matatu.objects.create(registration_number='KDC-003', operator='Ops')
        trip = ActiveTrip.objects.create(matatu=matatu, route=route, status=ActiveTrip.Status.ACTIVE)
        trip.current_latitude = -1.305   # between C2 and C3
        trip.current_longitude = 36.82
        trip.save()

        snapshot = _get_trip_tracking_snapshot(trip, list(route.stages.order_by('sequence_order')))
        self.assertEqual(snapshot['current_stage'].name, 'C2')   # last passed stage
        self.assertEqual(snapshot['next_stage'].name, 'C3')      # heading-to stage
