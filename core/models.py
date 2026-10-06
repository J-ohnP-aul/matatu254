from django.db import models


class SystemConfig(models.Model):
    """Key-value store for admin-configurable settings (notification thresholds, etc.)"""
    key = models.CharField(max_length=100, unique=True)
    value = models.TextField()
    description = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "System configs"

    def __str__(self):
        return self.key