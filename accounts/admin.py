from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User

# Register your models here.
@admin.register(User)

class CustomUserAdmin(UserAdmin):
  
  fieldsets = UserAdmin.fieldsets + (
    (
      "Additional infomation",
      {
        "fields": (
          "phone_number",
          "role",
        )
      },      
    ),
  )
  list_display = (
    "username",
    "phone_number",
    "role"
  )
  list_filter = (
    "role",
  )