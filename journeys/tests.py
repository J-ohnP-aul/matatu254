from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from types import SimpleNamespace
from unittest.mock import patch

from fleet.models import Matatu
from journeys.models import JourneySession
from r_outes.models import Route, Stage
from trips.models import ActiveTrip


class JourneyTrackingDataTests(TestCase):
	def setUp(self):
		self.passenger = get_user_model().objects.create_user(
			username="passenger", password="test-password"
		)
		route = Route.objects.create(name="Test Route")
		Stage.objects.create(
			route=route, name="Start", sequence_order=1,
			latitude=0, longitude=0.01,
		)
		destination = Stage.objects.create(
			route=route, name="Destination", sequence_order=2,
			latitude=0, longitude=0.02,
		)
		matatu = Matatu.objects.create(registration_number="KAA 001A", operator="Test")
		self.trip = ActiveTrip.objects.create(
			matatu=matatu,
			route=route,
			status=ActiveTrip.Status.ACTIVE,
		)
		self.trip.current_latitude = 0
		self.trip.current_longitude = 0
		self.trip.save(update_fields=["current_latitude", "current_longitude"])
		self.journey = JourneySession.objects.create(
			passenger=self.passenger,
			trip=self.trip,
			destination_stage=destination,
			status=JourneySession.Status.DESTINATION_SELECTED,
		)
		self.url = reverse("journeys:tracking-data", args=[self.journey.id])
		self.client.force_login(self.passenger)

	@patch("journeys.views.calculate_remaining")
	def test_tracking_endpoint_recalculates_from_latest_gps_position(self, calculate_remaining_mock):
		calculate_remaining_mock.side_effect = lambda vehicle_pos, *_: SimpleNamespace(
			distance_m=2000 - vehicle_pos[1] * 100000,
			distance_km=(2000 - vehicle_pos[1] * 100000) / 1000,
			duration_s=300,
			duration_minutes=5,
		)

		first_response = self.client.get(self.url)
		self.assertEqual(first_response.status_code, 200)
		self.assertEqual(first_response.json()["distance_m"], 2000)
		self.assertEqual(first_response.json()["next_stage_order"], 1)
		self.assertEqual(first_response.json()["progress_percent"], 0)

		page_response = self.client.get(
			reverse("journeys:journey-detail", args=[self.journey.id])
		)
		self.assertEqual(page_response.status_code, 200)
		self.assertContains(page_response, "Journey progress")
		self.assertContains(page_response, "Route stages")
		self.assertContains(page_response, "Destination")

		self.trip.current_longitude = 0.005
		self.trip.save(update_fields=["current_longitude"])
		second_response = self.client.get(self.url)

		self.assertEqual(second_response.status_code, 200)
		self.assertEqual(second_response.json()["distance_m"], 1500)
		self.assertEqual(calculate_remaining_mock.call_count, 3)

	def test_qr_and_destination_selection_resume_existing_active_journey(self):
		response = self.client.get(reverse("journeys:scan-qr"))
		self.assertRedirects(
			response,
			reverse("journeys:journey-detail", args=[self.journey.pk]),
		)

		response = self.client.post(
			reverse("journeys:select-destination", args=[self.trip.pk]),
			{"destination_stage_id": self.journey.destination_stage_id},
		)
		self.assertRedirects(
			response,
			reverse("journeys:journey-detail", args=[self.journey.pk]),
		)
		self.assertEqual(JourneySession.objects.filter(passenger=self.passenger).count(), 1)
