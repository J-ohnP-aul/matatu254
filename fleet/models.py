from django.db import models

# Create your models here.
from django.conf import settings

class Matatu(models.Model):
	registration_number = models.CharField(max_length=20, unique=True)
	operator = models.CharField(max_length=255)
	owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="matatus", null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	def __str__(self):
		return self.registration_number

class QRCode(models.Model):
	class Status(models.TextChoices):
		ACTIVE = "active", "Active"
		INACTIVE = "inactive", "Inactive"
	matatu = models.OneToOneField(
		Matatu,
		on_delete=models.CASCADE,
		related_name="qr_code",
	)
	code_value = models.TextField(unique=True)
	status = models.CharField(
		max_length=8,
		choices=Status.choices,
		default=Status.ACTIVE,
	)

	def __str__(self):
		return self.code_value
  
