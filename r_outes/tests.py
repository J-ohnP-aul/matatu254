from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from r_outes.models import Route, Stage


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

