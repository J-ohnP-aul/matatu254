from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from fleet.models import Matatu
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
