from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from fleet.models import Matatu
from journeys.models import JourneySession
from r_outes.models import Route, Stage
from trips.models import ActiveTrip

# Create your tests here.
class HomeViewTests(TestCase):
	def test_home_page_is_shown_to_anonymous_visitors(self):
		response = self.client.get(reverse("core:home"))

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "core/home.html")

	def test_passenger_dashboard_resumes_active_journey(self):
		passenger = User.objects.create_user(
			username="travelling-passenger",
			password="test-password",
			role=User.PASSANGER,
		)
		matatu = Matatu.objects.create(registration_number="KDA 1442", operator="Test")
		route = Route.objects.create(name="Passenger route")
		destination = Stage.objects.create(
			route=route,
			name="Destination",
			sequence_order=1,
			latitude=-1.0,
			longitude=36.0,
		)
		trip = ActiveTrip.objects.create(matatu=matatu, route=route)
		journey = JourneySession.objects.create(
			passenger=passenger,
			trip=trip,
			destination_stage=destination,
			status=JourneySession.Status.IN_TRANSIT,
		)
		self.client.force_login(passenger)

		response = self.client.get(reverse("core:dashboard"))

		self.assertRedirects(
			response,
			reverse("journeys:journey-detail", args=[journey.pk]),
		)

	def test_home_page_is_shown_to_authenticated_users(self):
		user = User.objects.create_user(
			username="passenger",
			phone_number="+254700000001",
			password="test-password",
		)
		self.client.force_login(user)

		response = self.client.get(reverse("core:home"))

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "core/home.html")
