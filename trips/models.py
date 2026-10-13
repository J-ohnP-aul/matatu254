from django.db import models
from django.utils import timezone

from fleet.models import Matatu
from r_outes.models import Route

# Create your models here.

GPS_STALE_AFTER_SECONDS = 60

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
  # --- current position cache ---
  current_latitude = models.DecimalField(
      max_digits=9, decimal_places=6, null=True, blank=True
  )
  current_longitude = models.DecimalField(
      max_digits=9, decimal_places=6, null=True, blank=True
  )
  last_ping_at = models.DateTimeField(null=True, blank=True)

  @property
  def gps_age_seconds(self):
    """Age of the latest location update, or None before the first ping."""
    if not self.last_ping_at:
      return None
    return max(0, int((timezone.now() - self.last_ping_at).total_seconds()))

  @property
  def is_stale(self):
    """Whether the latest location is missing or older than one minute."""
    age = self.gps_age_seconds
    return age is None or age > GPS_STALE_AFTER_SECONDS