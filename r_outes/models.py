# 
from django.db import models

from core.geo import haversine_distance_km


class Route(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(max_length=150, blank=True)

    def __str__(self):
        return f"{self.name}"

    @property
    def stage_count(self):
        return self.stages.count()

    @property
    def stage_list(self):
        return list(self.stages.order_by("sequence_order"))

class Stage(models.Model):
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="stages")
    name = models.CharField(max_length=100)
    sequence_order = models.PositiveIntegerField()
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)

    class Meta:
        ordering = ["route", "sequence_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["route", "sequence_order"],
                name="unique_stage_order_per_route",
            ),
        ]

    def __str__(self):
        return f"{self.route} #{self.sequence_order}: {self.name}"

    @property
    def label(self):
        return f"{self.sequence_order:02d}. {self.name}"

    @property
    def coordinates(self):
        return (self.latitude, self.longitude)

    @property
    def next_stage(self):
        return (
            Stage.objects
            .filter(route=self.route, sequence_order__gt=self.sequence_order)
            .order_by("sequence_order")
            .first()
        )

    @property
    def prev_stage(self):
        return (
            Stage.objects
            .filter(route=self.route, sequence_order__lt=self.sequence_order)
            .order_by("-sequence_order")
            .first()
        )

    @property
    def distance_from_previous_km(self):
        """Haversine (straight-line) distance from the previous stage.
        Used for 'closeness' context, not route-accurate ETA -- see
        routes/services.py for OSRM-backed road distance."""
        prev = self.prev_stage
        if not prev:
            return 0.0
        return round(haversine_distance_km(
            float(prev.latitude), float(prev.longitude),
            float(self.latitude), float(self.longitude),
        ), 3)

    @property
    def distance_to_next_km(self):
        """Haversine (straight-line) distance to the next stage."""
        following = self.next_stage
        if not following:
            return 0.0
        return round(haversine_distance_km(
            float(following.latitude), float(following.longitude),
            float(self.latitude), float(self.longitude),
        ), 3)
