from django.db import models
from django.contrib.auth.models import AbstractUser

# Create your models here

class User(AbstractUser):
  PASSANGER = 'PASSANGER'
  CONDUCTOR = 'CONDUCTOR'
  ADMIN = 'ADMIN'
  
  ROLE_CHOICES = [
    (PASSANGER, 'Passanger'),
    (CONDUCTOR, 'Conductor'),
    (ADMIN, 'Admin')
  ]
  phone_number = models.CharField(max_length=15, unique=True)
  role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=PASSANGER)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)
  def __str__(self):
      return f"{self.username} ({self.get_role_display()})"
  
  