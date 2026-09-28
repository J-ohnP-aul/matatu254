from django.contrib import admin

from .models import Matatu, QRCode
# Register your models here.

admin.site.register(Matatu)
admin.site.register(QRCode)
