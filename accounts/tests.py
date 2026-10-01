from django.test import TestCase
from django.urls import reverse

from .forms import CustomUserCreationForm
from .models import User

# Create your tests here.
class RegistrationTests(TestCase):
	def test_registration_form_only_contains_requested_fields(self):
		form = CustomUserCreationForm()

		self.assertEqual(list(form.fields), ["username", "email", "password1", "password2"])

	def test_registration_creates_passenger_without_phone_number(self):
		response = self.client.post(
			reverse("accounts:register"),
			{
				"username": "newpassenger",
				"email": "passenger@example.com",
				"password1": "Secure-Travel-92!",
				"password2": "Secure-Travel-92!",
			},
			follow=True,
		)

		self.assertRedirects(
			response,
			reverse("core:dashboard"),
		)
		self.assertTemplateUsed(response, "core/dashboard.html")
		self.assertTrue(response.context["user"].is_authenticated)
		user = User.objects.get(username="newpassenger")
		self.assertEqual(user.email, "passenger@example.com")
		self.assertEqual(user.role, User.PASSANGER)
		self.assertIsNone(user.phone_number)
		self.assertTrue(user.check_password("Secure-Travel-92!"))

	def test_registration_rejects_password_mismatch(self):
		response = self.client.post(
			reverse("accounts:register"),
			{
				"username": "mismatched",
				"email": "mismatched@example.com",
				"password1": "Secure-Travel-92!",
				"password2": "Different-Travel-93!",
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "The two password fields did not match.")
		self.assertFalse(User.objects.filter(username="mismatched").exists())
