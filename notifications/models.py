from django.db import models
from django.conf import settings

from journeys.models import JourneySession

# Create your models here.

class Notification(models.Model):
	class RecipientType(models.TextChoices):
		PASSENGER = "passenger", "Passenger"
		CONDUCTOR = "conductor", "Conductor"

	class Status(models.TextChoices):
		SENT = "sent", "Sent"
		READ = "read", "Read"
	recipient_type = models.CharField(
		max_length=9,
		choices=RecipientType.choices,
	)
	recipient_id = models.PositiveIntegerField()
	journey = models.ForeignKey(
		JourneySession,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		related_name="notifications",
	)
	message = models.TextField()
	timestamp = models.DateTimeField(auto_now_add=True)
	status = models.CharField(
		max_length=4,
		choices=Status.choices,
		default=Status.SENT,
	)

	def __str__(self):
		return f"{self.recipient_type}: {self.message[:50]}"

	def mark_read(self):
		self.status = self.Status.READ
		self.save(update_fields=["status"])


class PushSubscription(models.Model):
	"""A browser installation that can receive web push for one account."""
	user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions")
	endpoint = models.URLField(max_length=2048, unique=True)
	p256dh = models.CharField(max_length=255)
	auth = models.CharField(max_length=255)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-updated_at"]

