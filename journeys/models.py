from django.db import models

from accounts.models import User
from trips.models import ActiveTrip
from r_outes.models import Stage

# Create your models here.
class JourneySession(models.Model):
  class Status(models.TextChoices):
        INITIALIZED = "initiated", "Initiated"
        INTRANSIST = "intransist", "Intransist"
        APPROACHING = "approaching", "Approaching"
        ARRIVED = "arrived", "Arrived"
        ENDED = 'ended', "Ended"
        
  status = models.CharField(
            max_length=20,
            choices=Status.choices,
            default=Status.INITIALIZED,
          )
  
  user = models.ForeignKey(User, on_delete=models.CASCADE)
  trip_id = models.ForeignKey(ActiveTrip, on_delete=models.CASCADE)
  destination_stage = models.ForeignKey(Stage, on_delete=models.CASCADE)
  starttime = models.TimeField(auto_created=True)
  endtime = models.TimeField(null=True)
  
  