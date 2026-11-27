from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from r_outes.models import Route, Stage
from fleet.models import Matatu, QRCode
from journeys.models import JourneySession
from trips.models import ActiveTrip
from accounts.models import User as AppUser
from journeys.services import update_journey_status
from django.utils import timezone


class RouteManagementTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='adminuser',
            email='admin@example.com',
            password='testpass123',
            role='ADMIN',
        )

    def test_route_list_renders_with_stage_counts(self):
        route = Route.objects.create(name='Westlands', description='Test route')
        Stage.objects.create(
            route=route,
            name='CBD',
            sequence_order=1,
            latitude='-1.286389',
            longitude='36.817223',
        )
        Stage.objects.create(
            route=route,
            name='Kikuyu',
            sequence_order=2,
            latitude='-1.282000',
            longitude='36.870000',
        )

        self.client.login(username='adminuser', password='testpass123')
        response = self.client.get(reverse('management:route-list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Westlands')
        self.assertContains(response, '2')

    def test_dashboard_routes_cta_opens_route_management_list(self):
        self.client.login(username='adminuser', password='testpass123')
        response = self.client.get(reverse('management:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Manage routes')
        self.assertContains(response, reverse('management:route-list'))

    def test_dashboard_matatus_cta_opens_matatu_management_list(self):
        self.client.login(username='adminuser', password='testpass123')
        response = self.client.get(reverse('management:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Manage matatus')
        self.assertContains(response, reverse('management:matatu-list'))

    def test_stage_form_has_current_location_button(self):
        route = Route.objects.create(name='Nairobi Central', description='Test route')
        self.client.login(username='adminuser', password='testpass123')
        response = self.client.get(reverse('management:stage-create', args=[route.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Use current location')
        # Geolocation logic lives in the external stage-location.js bundle
        self.assertContains(response, 'stage-location.js')

    def test_stage_create_rejects_non_numeric_input_with_message(self):
        route = Route.objects.create(name='Nairobi Central', description='Test route')
        self.client.login(username='adminuser', password='testpass123')

        response = self.client.post(
            reverse('management:stage-create', args=[route.pk]),
            data={'name': 'Broken', 'sequence_order': 'one', 'latitude': '-1.28', 'longitude': '36.82'},
        )

        # A typo must surface as a friendly message, not an unhandled 500
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Stage.objects.filter(route=route).count(), 0)

    def test_stage_create_rejects_duplicate_sequence_order_with_message(self):
        route = Route.objects.create(name='Nairobi Central', description='Test route')
        Stage.objects.create(route=route, name='Taken', sequence_order=1, latitude='-1.28', longitude='36.82')
        self.client.login(username='adminuser', password='testpass123')

        response = self.client.post(
            reverse('management:stage-create', args=[route.pk]),
            data={'name': 'Dupe', 'sequence_order': '1', 'latitude': '-1.29', 'longitude': '36.83'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Stage.objects.filter(route=route).count(), 1)

    def test_stage_create_rejects_out_of_range_coordinates(self):
        route = Route.objects.create(name='Nairobi Central', description='Test route')
        self.client.login(username='adminuser', password='testpass123')

        response = self.client.post(
            reverse('management:stage-create', args=[route.pk]),
            data={'name': 'TooFar', 'sequence_order': '1', 'latitude': '999', 'longitude': '36.82'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Stage.objects.filter(route=route).count(), 0)



class LiveMapExploreTests(TestCase):
    """Live map, explore, and the live-vehicles feed (additive features)."""

    def setUp(self):
        self.user = AppUser.objects.create_user(username='rider', password='test-123', role='PASSANGER')
        self.matatu = Matatu.objects.create(registration_number='KDX-001', operator='Test Ops')
        self.route = Route.objects.create(name='Town - Estate')
        self.stage_a = Stage.objects.create(route=self.route, name='Town', sequence_order=1, latitude=-1.2921, longitude=36.8219)
        Stage.objects.create(route=self.route, name='Estate', sequence_order=2, latitude=-1.3000, longitude=36.8300)
        self.trip = ActiveTrip.objects.create(matatu=self.matatu, route=self.route, status=ActiveTrip.Status.ACTIVE)

    def test_live_vehicles_requires_login(self):
        response = self.client.get('/trips/live/')
        self.assertEqual(response.status_code, 302)

    def test_live_vehicles_returns_active_trip_with_position(self):
        self.trip.current_latitude = -1.2921
        self.trip.current_longitude = 36.8219
        self.trip.save()
        self.client.force_login(self.user)
        response = self.client.get('/trips/live/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['vehicles']), 1)
        vehicle = data['vehicles'][0]
        self.assertEqual(vehicle['registration'], 'KDX-001')
        self.assertAlmostEqual(vehicle['latitude'], -1.2921)

    def test_live_vehicles_excludes_positionless_trips(self):
        self.client.force_login(self.user)
        response = self.client.get('/trips/live/')
        self.assertEqual(response.json()['vehicles'], [])

    def test_live_map_page_renders(self):
        self.client.force_login(self.user)
        response = self.client.get('/map/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'routes-data')

    def test_live_map_dispatches_passenger_with_active_journey(self):
        # A passenger with an active journey gets their trip page from the
        # Map tab; the public radar remains for everyone else.
        self.client.force_login(self.user)
        self.trip.current_latitude = -1.2921
        self.trip.current_longitude = 36.8219
        self.trip.save()
        JourneySession.objects.create(
            passenger=self.user, trip=self.trip,
            destination_stage=Stage.objects.filter(route=self.route).first(),
            status=JourneySession.Status.IN_TRANSIT,
        )
        response = self.client.get('/map/')
        self.assertRedirects(response, f'/journeys/session/{JourneySession.objects.latest("id").id}/')

    def test_live_map_shows_public_radar_without_active_journey(self):
        self.client.force_login(self.user)
        response = self.client.get('/map/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'routes-data')

    def test_explore_page_renders_with_route_and_stages(self):
        self.client.force_login(self.user)
        response = self.client.get('/explore/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Town - Estate')

    def test_route_detail_renders(self):
        self.client.force_login(self.user)
        response = self.client.get(f'/explore/route/{self.route.pk}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'stage-list')


class JourneySwitchingTests(TestCase):
    """Scanning mid-journey: banner, and auto-switch on new stage pick."""

    def setUp(self):
        self.user = AppUser.objects.create_user(username='rider2', password='test-123', role='PASSANGER')
        self.matatu_a = Matatu.objects.create(registration_number='KDA-001', operator='Ops A')
        self.matatu_b = Matatu.objects.create(registration_number='KDB-002', operator='Ops B')
        self.route_a = Route.objects.create(name='Route A')
        self.stage_a1 = Stage.objects.create(route=self.route_a, name='A1', sequence_order=1, latitude=-1.29, longitude=36.82)
        Stage.objects.create(route=self.route_a, name='A2', sequence_order=2, latitude=-1.30, longitude=36.83)
        self.route_b = Route.objects.create(name='Route B')
        self.stage_b1 = Stage.objects.create(route=self.route_b, name='B1', sequence_order=1, latitude=-1.31, longitude=36.84)
        Stage.objects.create(route=self.route_b, name='B2', sequence_order=2, latitude=-1.32, longitude=36.85)
        self.trip_a = ActiveTrip.objects.create(matatu=self.matatu_a, route=self.route_a, status=ActiveTrip.Status.ACTIVE)
        self.trip_b = ActiveTrip.objects.create(matatu=self.matatu_b, route=self.route_b, status=ActiveTrip.Status.ACTIVE)
        QRCode.objects.create(matatu=self.matatu_b, code_value='MAT-0002', status=QRCode.Status.ACTIVE)
        self.journey = JourneySession.objects.create(
            passenger=self.user, trip=self.trip_a, destination_stage=self.stage_a1,
            status=JourneySession.Status.IN_TRANSIT,
        )
        self.client.force_login(self.user)

    def test_scan_page_reachable_with_active_journey(self):
        response = self.client.get('/journeys/scan/')
        self.assertEqual(response.status_code, 200)
        self.assertIn("already tracking", response.content.decode())

    def test_scan_result_processes_code_mid_journey(self):
        response = self.client.post('/journeys/scan/result/', {'code_value': 'MAT-0002'})
        self.assertRedirects(response, f'/journeys/trip/{self.trip_b.pk}/stages/')

    def test_new_stage_pick_closes_previous_journey(self):
        response = self.client.post(f'/journeys/trip/{self.trip_b.pk}/select/', {'destination_stage_id': self.stage_b1.pk})
        self.journey.refresh_from_db()
        self.assertEqual(self.journey.status, JourneySession.Status.ENDED)
        self.assertTrue(JourneySession.objects.filter(
            passenger=self.user, trip=self.trip_b, destination_stage=self.stage_b1,
        ).exclude(pk=self.journey.pk).exists())

    def test_same_matatu_resumes_existing_journey(self):
        response = self.client.post(f'/journeys/trip/{self.trip_a.pk}/select/', {'destination_stage_id': self.stage_a1.pk})
        self.journey.refresh_from_db()
        self.assertEqual(self.journey.status, JourneySession.Status.IN_TRANSIT)
        self.assertFalse(JourneySession.objects.exclude(pk=self.journey.pk).filter(passenger=self.user).exists())


class MonotonicProgressTests(TestCase):
    """Stage memory persists through transit and never un-completes."""

    def setUp(self):
        self.user = AppUser.objects.create_user(username='rider3', password='test-123', role='PASSANGER')
        self.route = Route.objects.create(name='Progress route')
        # Three stages ~1.1 km apart on a straight line
        self.stage1 = Stage.objects.create(route=self.route, name='P1', sequence_order=1, latitude=-1.290, longitude=36.820)
        self.stage2 = Stage.objects.create(route=self.route, name='P2', sequence_order=2, latitude=-1.300, longitude=36.820)
        self.stage3 = Stage.objects.create(route=self.route, name='P3', sequence_order=3, latitude=-1.310, longitude=36.820)
        self.matatu = Matatu.objects.create(registration_number='KDP-001', operator='Ops')
        self.trip = ActiveTrip.objects.create(matatu=self.matatu, route=self.route, status=ActiveTrip.Status.ACTIVE)
        self.journey = JourneySession.objects.create(
            passenger=self.user, trip=self.trip, destination_stage=self.stage3,
            status=JourneySession.Status.IN_TRANSIT,
        )

    def _ping(self, lat):
        self.trip.current_latitude = lat
        self.trip.current_longitude = 36.820
        self.trip.last_ping_at = timezone.now()
        self.trip.save()

    def test_reaching_stage_persists_completion(self):
        self._ping(-1.2905)  # at/past P1
        update_journey_status(self.journey)
        self.journey.refresh_from_db()
        self.assertIn(self.stage1.id, self.journey.completed_stage_ids)
        self.assertEqual(self.journey.current_stage_index, 0)

    def test_transit_between_stages_keeps_memory(self):
        self._ping(-1.2905)
        update_journey_status(self.journey)
        # Now halfway between P2 and P3 — nothing near either stage
        self._ping(-1.3055)
        update_journey_status(self.journey)
        self.journey.refresh_from_db()
        self.assertIn(self.stage1.id, self.journey.completed_stage_ids)
        self.assertIn(self.stage2.id, self.journey.completed_stage_ids)
        self.assertEqual(self.journey.current_stage_index, 1)

    def test_completion_never_regresses_on_bad_fix(self):
        self._ping(-1.3055)  # past P2
        update_journey_status(self.journey)
        # GPS glitch reports the vehicle back near P1
        self._ping(-1.2902)
        update_journey_status(self.journey)
        self.journey.refresh_from_db()
        self.assertIn(self.stage2.id, self.journey.completed_stage_ids)
        self.assertEqual(self.journey.current_stage_index, 1)  # stays at P2
        self.assertEqual(len(self.journey.completed_stage_ids), 2)

    def test_tracking_data_reports_persisted_state(self):
        self._ping(-1.3055)
        update_journey_status(self.journey)
        client = self.client_class()
        client.force_login(self.user)
        response = client.get(f'/journeys/session/{self.journey.pk}/tracking-data/')
        data = response.json()
        self.assertEqual(data['current_stage'], 'P2')
        self.assertEqual(data['next_stage'], 'P3')
        self.assertEqual(data['current_stage_index'], 1)
        self.assertEqual(len(data['completed_stage_ids']), 2)
