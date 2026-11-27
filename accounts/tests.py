from io import BytesIO

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
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

	def test_logout_logs_user_out(self):
		user = User.objects.create_user(
			username="loggedoutuser",
			email="logout@example.com",
			password="Secure-Travel-92!",
		)
		self.client.force_login(user)

		# GET must not log the user out (logout CSRF)
		get_response = self.client.get(reverse("accounts:logout"))
		self.assertEqual(get_response.status_code, 405)

		response = self.client.post(reverse("accounts:logout"), follow=True)

		self.assertRedirects(response, reverse("core:home"))
		self.assertFalse(response.context["user"].is_authenticated)

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


class ProfilePhotoTests(TestCase):
	def _image_upload(self):
		buffer = BytesIO()
		Image.new("RGB", (2, 2), color="blue").save(buffer, format="PNG")
		return SimpleUploadedFile("profile.png", buffer.getvalue(), content_type="image/png")

	@override_settings(MEDIA_ROOT="/tmp/matatu254-profile-test-media")
	def test_each_app_role_can_view_profile_photo_controls(self):
		for role in (User.PASSANGER, User.CONDUCTOR, User.ADMIN):
			with self.subTest(role=role):
				user = User.objects.create_user(
					username=f"profile-{role.lower()}",
					password="Secure-Travel-92!",
					role=role,
				)
				self.client.force_login(user)
				response = self.client.get(reverse("accounts:profile"))
				self.assertEqual(response.status_code, 200)
				self.assertContains(response, "Add or change photo")
				self.assertContains(response, user.username[0].upper())

	def test_profile_photo_upload_is_saved_and_shown_in_navigation(self):
		user = User.objects.create_user(
			username="photo-passenger",
			password="Secure-Travel-92!",
			role=User.PASSANGER,
		)
		self.client.force_login(user)

		with override_settings(MEDIA_ROOT="/tmp/matatu254-profile-test-media"):
			response = self.client.post(
				reverse("accounts:profile"),
				{"profile_image": self._image_upload()},
				follow=True,
			)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Your profile photo was updated.")
		user.refresh_from_db()
		self.assertTrue(user.profile_image.name.startswith("profile_images/"))
		self.assertContains(response, user.profile_image.url)

	def test_profile_photo_rejects_files_over_five_megabytes(self):
		user = User.objects.create_user(
			username="large-photo-passenger",
			password="Secure-Travel-92!",
		)
		self.client.force_login(user)
		image = self._image_upload()
		image_content = image.read()
		oversized_image = SimpleUploadedFile(
			"large-profile.png",
			image_content + (b" " * (5 * 1024 * 1024)),
			content_type="image/png",
		)

		response = self.client.post(
			reverse("accounts:profile"),
			{"profile_image": oversized_image},
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Choose an image smaller than 5 MB.")
		user.refresh_from_db()
		self.assertFalse(user.profile_image)
