from django.db import models
from django.contrib.auth.models import AbstractUser
from django.conf import settings

# Create your models here

class User(AbstractUser):
  PASSANGER = 'PASSANGER'
  CONDUCTOR = 'CONDUCTOR'
  ADMIN = 'ADMIN'
  
  ROLE_CHOICES = [
    (PASSANGER, 'Passenger'),
    (CONDUCTOR, 'Conductor'),
    (ADMIN, 'Admin')
  ]
  phone_number = models.CharField(max_length=15, unique=True, blank=True, null=True)
  role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=PASSANGER)
  matatu = models.ForeignKey(
    'fleet.Matatu',
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name='conductor',
    help_text='Matatu assigned to this conductor (1:1 per MVP)'
  )
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)
  
  def __str__(self):
      return f"{self.username} ({self.get_role_display()})"
  
  