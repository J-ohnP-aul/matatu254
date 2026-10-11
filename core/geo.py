"""Pure, dependency-free geospatial helpers for route and stage calculations."""

import math

EARTH_RADIUS_M = 6_371_000  # mean Earth radius in meters

__all__ = ["EARTH_RADIUS_M", "haversine_distance_m", "haversine_distance_km"]


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the straight-line distance between two GPS points in meters."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_M * c


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the straight-line distance between two GPS points in kilometers."""
    return haversine_distance_m(lat1, lon1, lat2, lon2) / 1000