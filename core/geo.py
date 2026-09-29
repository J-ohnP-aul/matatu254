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



# # open street maps api to solve the distance under difrent routes and the aproximate time


# # Coordinates: OSRM uses (longitude, latitude) format
# origin = "34.777061,-0.680482"      # Kisii Town (lon,lat)
# destination = "34.598330,-0.756750" # Rongo (lon,lat)

# # Correct OSRM demo server URL structure
# url = f"http://router.project-osrm.org/route/v1/driving/{origin};{destination}?overview=false"

# response = requests.get(url).json()

# if response.get("code") == "Ok":
#     # OSRM returns distance in meters and duration in seconds
#     distance_meters = response["routes"][0]["distance"]
#     duration_seconds = response["routes"][0]["duration"]

#     print(f"Road Distance: {distance_meters / 1000:.2f} km")
#     print(f"Travel Time: {duration_seconds / 60:.1f} mins")
# else:
#     print("Error from OSRM API:", response.get("message", "Unknown error"))
    



import requests
from dataclasses import dataclass
from typing import Optional


OSRM_BASE_URL = "http://router.project-osrm.org/route/v1/driving"
DEFAULT_TIMEOUT = 10  # seconds


@dataclass
class RouteInfo:
    """Result of a routing query between two points."""
    distance_km: float
    duration_minutes: float
    distance_meters: float
    duration_seconds: float


class OSRMError(Exception):
    """Raised when the OSRM API returns an error or is unreachable."""
    pass


def get_route_info(
    origin: tuple[float, float],
    destination: tuple[float, float],
    timeout: int = DEFAULT_TIMEOUT,
) -> Optional[RouteInfo]:
    """
    Calculate road distance and travel time between two coordinates using OSRM.

    Args:
        origin: (longitude, latitude) of the starting point.
        destination: (longitude, latitude) of the ending point.
        timeout: Request timeout in seconds.

    Returns:
        RouteInfo with distance (km) and duration (minutes), or None on failure.

    Raises:
        OSRMError: If the API returns an error code or the request fails.
    """
    # OSRM expects "lon,lat;lon,lat" in the URL path
    coords = f"{origin[0]},{origin[1]};{destination[0]},{destination[1]}"
    url = f"{OSRM_BASE_URL}/{coords}"
    params = {"overview": "false", "alternatives": "false", "steps": "false"}

    try:
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as e:
        raise OSRMError(f"Request to OSRM failed: {e}") from e

    try:
        data = response.json()
    except ValueError as e:
        raise OSRMError(f"Invalid JSON from OSRM: {e}") from e

    if data.get("code") != "Ok":
        message = data.get("message", "Unknown error")
        raise OSRMError(f"OSRM error: {message}")

    routes = data.get("routes")
    if not routes:
        raise OSRMError("OSRM returned no routes")

    route = routes[0]
    distance_m = route["distance"]
    duration_s = route["duration"]

    return RouteInfo(
        distance_meters=distance_m,
        duration_seconds=duration_s,
        distance_km=distance_m / 1000,
        duration_minutes=duration_s / 60,
    )


def format_duration(minutes: float) -> str:
    """Format minutes into a human-readable 'Xh Ym' or 'Y mins' string."""
    total_minutes = round(minutes)
    if total_minutes < 60:
        return f"{total_minutes} min" + ("s" if total_minutes != 1 else "")
    hours, mins = divmod(total_minutes, 60)
    if mins == 0:
        return f"{hours}h"
    return f"{hours}h {mins}m"


if __name__ == "__main__":
    # Kisii Town -> Rongo (longitude, latitude)
    origin = (34.777061, -0.680482)
    destination = (34.598330, -0.756750)

    try:
        route = get_route_info(origin, destination)
        print(f"Distance: {route.distance_km:.2f} km")
        print(f"Duration: {format_duration(route.duration_minutes)}")
    except OSRMError as e:
        print(f"Routing failed: {e}")