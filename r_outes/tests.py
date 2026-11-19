from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from r_outes.models import Route, Stage
from fleet.models import Matatu
from trips.models import ActiveTrip
from accounts.models import User as AppUser


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
        self.assertContains(response, 'Manage Routes')
        self.assertContains(response, reverse('management:route-list'))
        self.assertNotContains(response, reverse('management:route-create'))

    def test_dashboard_matatus_cta_opens_matatu_management_list(self):
        self.client.login(username='adminuser', password='testpass123')
        response = self.client.get(reverse('management:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Manage Matatus')
        self.assertContains(response, reverse('management:matatu-list'))
        self.assertNotContains(response, reverse('management:matatu-create'))

    def test_stage_form_has_current_location_button(self):
        route = Route.objects.create(name='Nairobi Central', description='Test route')
        self.client.login(username='adminuser', password='testpass123')
        response = self.client.get(reverse('management:stage-create', args=[route.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Use current location')
        self.assertContains(response, 'navigator.geolocation')



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
