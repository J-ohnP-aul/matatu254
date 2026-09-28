from django.db import models


# Create your models here.

class Route(models.Model):
    name = models.TextField(max_length=20, unique=True)
    description = models.TextField(max_length=150, blank=True)

    def __str__(self):
        return f"{self.name}"

class Stage(models.Model):
    route = models.ForeignKey(Route, on_delete=models.CASCADE)       # creates route_id column
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
    