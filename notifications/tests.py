from decimal import Decimal
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from fleet.models import Matatu
from journeys.models import JourneySession
from journeys.services import update_journey_status
from notifications.models import Notification, PushSubscription
from notifications.signals import send_web_push
from r_outes.models import Route, Stage
from trips.models import ActiveTrip
from trips.services import complete_trip, record_ping

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


@override_settings(
    WEBPUSH_VAPID_PUBLIC_KEY="test-public-key",
    WEBPUSH_VAPID_PRIVATE_KEY="test-private-key",
    WEBPUSH_VAPID_SUBJECT="mailto:ops@example.com",
    WEBPUSH_ASYNC=False,
)
class WebPushBehaviorTests(TestCase):
    def setUp(self):
        self.passenger = User.objects.create_user(
            username="push_passenger",
            password="secret123",
            role=User.PASSANGER,
        )
        self.conductor = User.objects.create_user(
            username="push_conductor",
            password="secret123",
            role=User.CONDUCTOR,
        )
        self.admin = User.objects.create_user(
            username="push_admin",
            password="secret123",
            role=User.ADMIN,
        )
        self.matatu = Matatu.objects.create(
            registration_number="KDA 254P",
            operator="City Shuttle",
        )
        self.conductor.matatu = self.matatu
        self.conductor.save()

        self.route = Route.objects.create(name="Ngong Road")
        self.stage_one = Stage.objects.create(
            route=self.route,
            name="Prestige",
            sequence_order=1,
            latitude=Decimal("-1.299000"),
            longitude=Decimal("36.787000"),
        )
        self.destination = Stage.objects.create(
            route=self.route,
            name="Junction",
            sequence_order=2,
            latitude=Decimal("-1.298000"),
            longitude=Decimal("36.762000"),
        )
        self.trip = ActiveTrip.objects.create(
            matatu=self.matatu,
            route=self.route,
            status=ActiveTrip.Status.ACTIVE,
        )
        self.journey = JourneySession.objects.create(
            passenger=self.passenger,
            trip=self.trip,
            destination_stage=self.destination,
            status=JourneySession.Status.IN_TRANSIT,
        )
        self.passenger_sub = PushSubscription.objects.create(
            user=self.passenger,
            endpoint="https://fcm.googleapis.com/fcm/send/passenger-1",
            p256dh="p256dh-passenger",
            auth="auth-passenger",
        )
        self.conductor_sub = PushSubscription.objects.create(
            user=self.conductor,
            endpoint="https://fcm.googleapis.com/fcm/send/conductor-1",
            p256dh="p256dh-conductor",
            auth="auth-conductor",
        )

    @patch("pywebpush.webpush")
    def test_only_arrived_notifications_trigger_web_push_and_link_live_journey(self, mock_webpush):
        with self.captureOnCommitCallbacks(execute=True):
            record_ping(
                self.trip,
                latitude=self.stage_one.latitude,
                longitude=self.stage_one.longitude,
            )

        reached = Notification.objects.get(
            recipient_type=Notification.RecipientType.PASSENGER,
            recipient_id=self.passenger.pk,
            message="Reached Prestige",
        )
        self.assertFalse(reached.send_push)
        mock_webpush.assert_not_called()

        # First ping near destination transitions IN_TRANSIT -> APPROACHING (in-app only)
        with self.captureOnCommitCallbacks(execute=True):
            record_ping(
                self.trip,
                latitude=self.destination.latitude,
                longitude=self.destination.longitude,
            )
        approaching = Notification.objects.get(
            recipient_type=Notification.RecipientType.PASSENGER,
            recipient_id=self.passenger.pk,
            message="Approaching Junction — prepare to alight",
        )
        self.assertFalse(approaching.send_push)
        mock_webpush.assert_not_called()

        # Next update at destination transitions APPROACHING -> ARRIVED (triggers pop-up)
        self.journey.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            update_journey_status(self.journey)

        self.journey.refresh_from_db()
        self.assertEqual(self.journey.status, JourneySession.Status.ARRIVED)
        self.assertEqual(mock_webpush.call_count, 2)

        payloads = {
            call.kwargs["subscription_info"]["endpoint"]: json.loads(call.kwargs["data"])
            for call in mock_webpush.call_args_list
        }
        passenger_payload = payloads[self.passenger_sub.endpoint]
        self.assertEqual(
            passenger_payload["url"],
            reverse("journeys:journey-detail", args=[self.journey.pk]),
        )
        self.assertTrue(passenger_payload["urgent"])
        self.assertIn("Junction", passenger_payload["body"])

        conductor_payload = payloads[self.conductor_sub.endpoint]
        self.assertEqual(conductor_payload["url"], reverse("conductor:notifications"))
        self.assertIn("Junction", conductor_payload["body"])

    @patch("pywebpush.webpush")
    def test_ending_trip_notifies_conductor_and_triggers_web_push(self, mock_webpush):
        self.client.force_login(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("management:trip-end", args=[self.trip.pk]))

        self.assertEqual(response.status_code, 302)
        self.trip.refresh_from_db()
        self.journey.refresh_from_db()
        self.assertEqual(self.trip.status, ActiveTrip.Status.COMPLETED)
        self.assertEqual(self.journey.status, JourneySession.Status.ENDED)

        conductor_notification = Notification.objects.get(
            recipient_type=Notification.RecipientType.CONDUCTOR,
            recipient_id=self.conductor.pk,
            message="Trip ended: Ngong Road (KDA 254P)",
        )
        self.assertTrue(conductor_notification.send_push)
        mock_webpush.assert_called_once()
        payload = json.loads(mock_webpush.call_args.kwargs["data"])
        self.assertEqual(payload["title"], "Trip ended")
        self.assertEqual(payload["url"], reverse("conductor:notifications"))

    @patch("pywebpush.webpush")
    def test_cancelling_trip_notifies_conductor(self, mock_webpush):
        with self.captureOnCommitCallbacks(execute=True):
            closed = complete_trip(self.trip, cancelled=True)

        self.assertTrue(closed)
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.status, ActiveTrip.Status.CANCELLED)
        self.assertTrue(
            Notification.objects.filter(
                recipient_type=Notification.RecipientType.CONDUCTOR,
                recipient_id=self.conductor.pk,
                message="Trip cancelled: Ngong Road (KDA 254P)",
                send_push=True,
            ).exists()
        )
        mock_webpush.assert_called_once()

    @patch("pywebpush.webpush")
    def test_expired_subscription_is_deleted_on_410(self, mock_webpush):
        from pywebpush import WebPushException

        mock_webpush.side_effect = WebPushException(
            "Gone",
            response=SimpleNamespace(status_code=410),
        )
        note = Notification.objects.create(
            recipient_type=Notification.RecipientType.PASSENGER,
            recipient_id=self.passenger.pk,
            journey=self.journey,
            message="You have arrived at your destination: Junction",
            send_push=True,
        )
        send_web_push(note.pk)

        self.assertFalse(PushSubscription.objects.filter(pk=self.passenger_sub.pk).exists())

    @patch("pywebpush.webpush")
    def test_push_subscription_and_test_endpoint(self, mock_webpush):
        self.client.force_login(self.passenger)

        get_resp = self.client.get(reverse("notifications:push-subscription"))
        self.assertEqual(get_resp.status_code, 200)
        self.assertEqual(get_resp.json()["publicKey"], "test-public-key")

        post_resp = self.client.post(
            reverse("notifications:push-subscription"),
            data=json.dumps({
                "endpoint": "https://fcm.googleapis.com/fcm/send/passenger-2",
                "keys": {"p256dh": "k1", "auth": "a1"},
            }),
            content_type="application/json",
        )
        self.assertEqual(post_resp.status_code, 200)
        self.assertTrue(
            PushSubscription.objects.filter(
                user=self.passenger,
                endpoint="https://fcm.googleapis.com/fcm/send/passenger-2",
            ).exists()
        )

        test_resp = self.client.post(reverse("notifications:push-test"))
        self.assertEqual(test_resp.status_code, 200)
        self.assertEqual(test_resp.json()["sent"], 2)
        self.assertEqual(mock_webpush.call_count, 2)

        del_resp = self.client.delete(
            reverse("notifications:push-subscription"),
            data=json.dumps({"endpoint": "https://fcm.googleapis.com/fcm/send/passenger-2"}),
            content_type="application/json",
        )
        self.assertEqual(del_resp.status_code, 200)
        self.assertFalse(
            PushSubscription.objects.filter(
                endpoint="https://fcm.googleapis.com/fcm/send/passenger-2"
            ).exists()
        )

    def test_tracking_and_conductor_dashboard_render_push_controls(self):
        self.client.force_login(self.passenger)
        journey_resp = self.client.get(reverse("journeys:journey-detail", args=[self.journey.pk]))
        self.assertEqual(journey_resp.status_code, 200)
        self.assertContains(journey_resp, "data-push-controls")
        self.assertContains(journey_resp, 'data-public-key="test-public-key"')

        self.client.force_login(self.conductor)
        dash_resp = self.client.get(reverse("conductor:dashboard"))
        self.assertEqual(dash_resp.status_code, 200)
        self.assertContains(dash_resp, "data-push-controls")
        self.assertContains(dash_resp, 'data-public-key="test-public-key"')
