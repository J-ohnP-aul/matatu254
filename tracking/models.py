from django.db import models

from trips.models import ActiveTrip

# Create your models here.

class TripLocationLog(models.Model):
  trip = models.ForeignKey(ActiveTrip, on_delete=models.CASCADE)
  latitude = models.DecimalField(max_digits=9, decimal_places=6)
  longitude = models.DecimalField(max_digits=9, decimal_places=6)
  recorded_at = models.DateTimeField(auto_now_add=True)
  
  