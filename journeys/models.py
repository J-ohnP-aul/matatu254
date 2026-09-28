from django.db import models

from accounts.models import User
from trips.models import ActiveTrip
from r_outes.models import Stage

# Create your models here.
class JourneySession(models.Model):
  class Status(models.TextChoices):
            INITIALIZED = "initiated", "Initiated"
            DESTINATION_SELECTED = "destination_selected", "Destination selected"
            IN_TRANSIT = "in_transit", "In transit"
            APPROACHING = "approaching", "Approaching"
            ARRIVED = "arrived", "Arrived"
            ENDED = "ended", "Ended"
        
  status = models.CharField(
            max_length=20,
            choices=Status.choices,
            default=Status.INITIALIZED,
          )
  
  passenger = models.ForeignKey(User, on_delete=models.CASCADE)
  trip = models.ForeignKey(ActiveTrip, on_delete=models.CASCADE)
  destination_stage = models.ForeignKey(Stage, on_delete=models.CASCADE)
  start_time = models.DateTimeField(auto_now_add=True)
  end_time = models.DateTimeField(null=True, blank=True)
  
  