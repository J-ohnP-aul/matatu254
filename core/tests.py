from django.test import TestCase
from django.urls import reverse

from accounts.models import User

# Create your tests here.
class HomeViewTests(TestCase):
	def test_home_page_is_shown_to_anonymous_visitors(self):
		response = self.client.get(reverse("core:home"))

		self.assertEqual(response.status_code, 200)
		self.assertTemplateUsed(response, "core/home.html")

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
