from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from fleet.models import Matatu
from journeys.models import JourneySession
from journeys.services import update_journey_status
from notifications.models import Notification
from r_outes.models import Route, Stage
from trips.models import ActiveTrip

User = get_user_model()


class NotificationBusinessLogicTests(TestCase):
    def setUp(self):
        self.passenger = User.objects.create_user(
            username='passenger1',
            password='secret123',
            role=User.PASSANGER,
        )
        self.conductor = User.objects.create_user(
            username='conductor1',
            password='secret123',
            role=User.CONDUCTOR,
        )
        self.matatu = Matatu.objects.create(
            registration_number='KAA 123A',
            operator='City Shuttle',
        )
        self.conductor.matatu = self.matatu
        self.conductor.save()

        self.route = Route.objects.create(name='Westlands Route')
        self.stage_one = Stage.objects.create(
            route=self.route,
            name='Westlands',
            sequence_order=1,
            latitude=Decimal('-1.283300'),
            longitude=Decimal('36.816700'),
        )
        self.destination = Stage.objects.create(
            route=self.route,
            name='Kibera',
            sequence_order=2,
            latitude=Decimal('-1.283301'),
            longitude=Decimal('36.816701'),
        )
        self.trip = ActiveTrip.objects.create(
            matatu=self.matatu,
            route=self.route,
            status=ActiveTrip.Status.ACTIVE,
            current_latitude=self.destination.latitude,
            current_longitude=self.destination.longitude,
        )
        self.journey = JourneySession.objects.create(
            passenger=self.passenger,
            trip=self.trip,
            destination_stage=self.destination,
            status=JourneySession.Status.IN_TRANSIT,
        )

    def test_approaching_notification_is_created_for_passenger_and_conductor(self):
        updated = update_journey_status(self.journey)

        self.assertEqual(updated.status, JourneySession.Status.APPROACHING)
        self.assertTrue(
            Notification.objects.filter(
                recipient_type=Notification.RecipientType.PASSENGER,
                recipient_id=self.passenger.pk,
                journey=self.journey,
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient_type=Notification.RecipientType.CONDUCTOR,
                recipient_id=self.conductor.pk,
                journey=self.journey,
            ).exists()
        )

    def test_passenger_notifications_page_lists_current_user_notifications(self):
        Notification.objects.create(
            recipient_type=Notification.RecipientType.PASSENGER,
            recipient_id=self.passenger.pk,
            journey=self.journey,
            message='Approaching Kibera — prepare to alight',
        )

        self.client.login(username='passenger1', password='secret123')
        response = self.client.get(reverse('notifications:list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Approaching Kibera')
