# import requests
# from pygreatcircledistance import (
#  haversine_formula,
#  spherical_law_of_cosines_formula,
#  vincenty_formula,
# )

# # straight line btwn cordinates 
# distance_m = haversine_formula( # best for shrt stage calculations
#   (-0.756750, 34.598330),  #rongo
#   (-0.680482, 34.777061), #kisii town
# )

# print(distance_m/1000)

"""
core/geo.py

Pure, dependency-free distance calculations. No network calls, no DB access.

Used for anything that needs to be fast and run often -- e.g. checking
whether a vehicle is "close enough" to a stage to count as having reached it.
For road-accurate distance/duration (slower, network-dependent), see
core/osrm_client.py instead.
"""
import math

EARTH_RADIUS_M = 6_371_000  # mean Earth radius in meters


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Straight-line ("as the crow flies") distance between two GPS points,
    in meters, using the Haversine formula.

    Accepts plain floats so callers don't need to know about Decimal fields
    on the Stage model -- convert at the call site.
    """
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
    """Convenience wrapper returning kilometers instead of meters."""
    return haversine_distance_m(lat1, lon1, lat2, lon2) / 1000


