from django.db import models

from fleet.models import Matatu
from r_outes.models import Route

# Create your models here.

class ActiveTrip(models.Model):
  class Status(models.TextChoices):
      ACTIVE = "active", "Active"
      INACTIVE = "inactive", "Inactive"
      
  mat_id = models.ForeignKey(Matatu, on_delete=models.CASCADE)
  route_id = models.ForeignKey(Route, on_delete=models.CASCADE)
  starttime = models.TimeField(auto_created=True)
  endtime = models.TimeField(null=True)
  status = models.CharField(
      max_length=8,
      choices=Status.choices,
      default=Status.ACTIVE,
    )
   