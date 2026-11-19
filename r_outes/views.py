"""
r_outes/views.py — Explore (route & stage discovery) and the public Live Map.

These views reuse the real Route/Stage/ActiveTrip data and the existing
OSRM-backed helpers. No data is invented; route geometry comes from OSRM
(cached per route) with the stage coordinates as the honest fallback.
"""
import time

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404

from .models import Route
from .routes_services import get_route_polyline

# Encoded OSRM overview polyline per route. Stage geometry changes rarely,
# and the journey screens already treat the polyline as cacheable context.
_GEOMETRY_TTL_S = 600
_geometry_cache: dict[int, tuple[str, float]] = {}


def _route_geometry(route, stages):
    """Encoded OSRM polyline for the route, or '' when unavailable."""
    cached = _geometry_cache.get(route.pk)
    if cached:
        polyline, cached_at = cached
        if time.monotonic() - cached_at < _GEOMETRY_TTL_S:
            return polyline
    polyline = ""
    if len(stages) >= 2:
        first, last = stages[0], stages[-1]
        polyline = get_route_polyline(
            (float(first.longitude), float(first.latitude)),
            (float(last.longitude), float(last.latitude)),
        ) or ""
    if polyline:
        _geometry_cache[route.pk] = (polyline, time.monotonic())
    return polyline


def _route_payload(route):
    """One route with its ordered stages, in the shape the map JS expects."""
    stages = list(route.stages.order_by("sequence_order"))
    return {
        "id": route.pk,
        "name": route.name,
        "description": route.description,
        "geometry": _route_geometry(route, stages),
        "stages": [
            {
                "id": stage.pk,
                "name": stage.name,
                "sequenceOrder": stage.sequence_order,
                "latitude": float(stage.latitude),
                "longitude": float(stage.longitude),
            }
            for stage in stages
        ],
    }


@login_required
def live_map(request):
    """Public live map: all routes + stages embedded, vehicles polled live."""
    routes = [
        _route_payload(route)
        for route in Route.objects.prefetch_related("stages").order_by("name")
    ]
    return render(request, "r_outes/live_map.html", {
        "routes": routes,
    })


@login_required
def explore(request):
    """Route and stage discovery home."""
    routes = [
        _route_payload(route)
        for route in Route.objects.prefetch_related("stages").order_by("name")
    ]
    stages = []
    for route in routes:
        for stage in route["stages"]:
            stages.append({**stage, "routeId": route["id"], "routeName": route["name"]})
    return render(request, "r_outes/explore.html", {
        "routes": routes,
        "stages": stages,
    })


@login_required
def route_detail(request, pk):
    """One route: map, ordered stages, and vehicles currently on it."""
    route = get_object_or_404(Route.objects.prefetch_related("stages"), pk=pk)
    payload = _route_payload(route)
    return render(request, "r_outes/route_detail.html", {
        "route": route,
        "stages": payload["stages"],
        "route_payload": payload,
    })
