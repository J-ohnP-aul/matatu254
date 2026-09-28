from django.db import models

from trips.models import ActiveTrip

# Create your models here.

class Trip_loc_log(models.Model):
  trip_id = models.ForeignKey(ActiveTrip, on_delete=models.CASCADE)
  latitude = models.DecimalField(max_digits=9, decimal_places=6)
  longitude = models.DecimalField(max_digits=9, decimal_places=6)
  recorded_at = models.TimeField(auto_now_add=True)
  
  