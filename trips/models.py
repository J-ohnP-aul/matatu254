from django.db import models

from fleet.models import Matatu
from r_outes.models import Route

# Create your models here.

class ActiveTrip(models.Model):
  class Status(models.TextChoices):
    CREATED = "created", "Created"
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"
      
  matatu = models.ForeignKey(Matatu, on_delete=models.CASCADE)
  route = models.ForeignKey(Route, on_delete=models.CASCADE)
  start_time = models.DateTimeField(auto_now_add=True)
  end_time = models.DateTimeField(null=True, blank=True)
  status = models.CharField(
    max_length=9,
    choices=Status.choices,
    default=Status.CREATED,
  )
   