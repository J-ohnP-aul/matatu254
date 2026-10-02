from django.db import models
from django.utils import timezone

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
  # --- current position cache ---
  current_latitude = models.DecimalField(
      max_digits=9, decimal_places=6, null=True, blank=True
  )
  current_longitude = models.DecimalField(
      max_digits=9, decimal_places=6, null=True, blank=True
  )
  last_ping_at = models.DateTimeField(null=True, blank=True)

  @property
  def is_stale(self, threshold_seconds=60):
    """True if we haven't heard from the device recently."""
    if not self.last_ping_at:
      return True
    age = (timezone.now() - self.last_ping_at).total_seconds()
    return age > threshold_seconds