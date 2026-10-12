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
from trips.services import record_ping

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
            latitude=Decimal('-1.285300'),
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

    def test_fresh_gps_pings_notify_passenger_of_intermediate_stage_once(self):
        record_ping(
            self.trip,
            latitude=self.stage_one.latitude,
            longitude=self.stage_one.longitude,
        )
        record_ping(
            self.trip,
            latitude=self.stage_one.latitude,
            longitude=self.stage_one.longitude,
        )

        self.assertEqual(
            Notification.objects.filter(
                recipient_type=Notification.RecipientType.PASSENGER,
                recipient_id=self.passenger.pk,
                journey=self.journey,
                message="Reached Westlands",
            ).count(),
            1,
        )

    def test_destination_arrival_creates_passenger_notification(self):
        update_journey_status(self.journey)
        self.journey.refresh_from_db()
        update_journey_status(self.journey)
        self.journey.refresh_from_db()

        self.assertEqual(self.journey.status, JourneySession.Status.ARRIVED)
        self.assertTrue(Notification.objects.filter(
            recipient_type=Notification.RecipientType.PASSENGER,
            recipient_id=self.passenger.pk,
            journey=self.journey,
            message="You have arrived at your destination: Kibera",
        ).exists())

    def test_tracking_data_includes_latest_journey_notification(self):
        self.trip.current_latitude = None
        self.trip.current_longitude = None
        self.trip.save(update_fields=["current_latitude", "current_longitude"])
        notification = Notification.objects.create(
            recipient_type=Notification.RecipientType.PASSENGER,
            recipient_id=self.passenger.pk,
            journey=self.journey,
            message="Reached Westlands",
        )
        self.client.force_login(self.passenger)

        response = self.client.get(
            reverse("journeys:tracking-data", args=[self.journey.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["latest_notification"], {
            "id": notification.pk,
            "message": "Reached Westlands",
        })
