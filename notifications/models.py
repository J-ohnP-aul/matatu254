from django.db import models

from journeys.models import JourneySession
from accounts.models import User
# Create your models here.

class Notification(models.Model):
	class RecipientType(models.TextChoices):
		PASSENGER = "passenger", "Passenger"
		CONDUCTOR = "conductor", "Conductor"

	class Status(models.TextChoices):
		SENT = "sent", "Sent"
	recipient_type = models.CharField(
		max_length=9,
		choices=RecipientType.choices,
	)
	recipient_id = models.ForeignKey(
    User,
    on_delete=models.CASCADE
  )
	journey_id = models.ForeignKey(
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

