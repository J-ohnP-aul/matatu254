"""
routes/services.py

Two distinct concerns, kept separate on purpose:

1. is_near_stage() -- Haversine, no network call. Safe to run on every
   incoming GPS ping to check "has the vehicle reached this stage?".

2. get_segment_road_distance() / remaining_road_distance() -- OSRM-backed,
   one network call per segment. Call these when the journey screen needs
   a distance/ETA figure, NOT inside the per-ping location handler.

Both fall back to Haversine automatically if OSRM is unreachable, so a
flaky local OSRM instance degrades the numbers rather than breaking the
journey screen (see NFR-R-02).
"""
from core.geo import haversine_distance_m
from core.osrm import OSRMError, RouteInfo, get_route_info
from django.conf import settings
import requests
import time

# How close (meters) the vehicle must be to a stage to count as "reached".
# MVP constant for now; move to system_config once the admin threshold
# screens (FR-A-07) exist.
STAGE_ARRIVAL_RADIUS_M = 20

# Road distance between two stages rarely changes, but it is requested on
# every tracking poll. Cache OSRM segment results per stage pair for a few
# minutes so a poll never blocks on N sequential OSRM round-trips.
_SEGMENT_CACHE_TTL_S = 600
_segment_cache: dict[tuple[int, int], tuple[RouteInfo, float]] = {}


def is_near_stage(vehicle_lat: float, vehicle_lon: float, stage) -> bool:
    """
    Cheap proximity check -- call this on every GPS ping to decide whether
    the vehicle has reached `stage`. Pure Haversine, no network call.
    """
    distance = haversine_distance_m(
        vehicle_lat, vehicle_lon, float(stage.latitude), float(stage.longitude)
    )
    return distance <= STAGE_ARRIVAL_RADIUS_M


def get_segment_road_distance(stage_a, stage_b) -> RouteInfo:
    """
    Road distance + duration between two stages, via OSRM. Falls back to a
    straight-line Haversine estimate (with a rough speed assumption for
    duration) if OSRM is unreachable, so callers always get a RouteInfo
    back rather than having to handle OSRMError themselves.
    """
    cache_key = (stage_a.id, stage_b.id)
    cached = _segment_cache.get(cache_key)
    if cached:
        route_info, cached_at = cached
        if time.monotonic() - cached_at < _SEGMENT_CACHE_TTL_S:
            return route_info

    origin = (float(stage_a.longitude), float(stage_a.latitude))
    destination = (float(stage_b.longitude), float(stage_b.latitude))

    try:
        route_info = get_route_info(origin, destination)
    except OSRMError:
        # Fallback: straight-line distance, assume a flat average speed
        # (25 km/h) to still produce a usable duration estimate.
        distance_m = haversine_distance_m(
            float(stage_a.latitude), float(stage_a.longitude),
            float(stage_b.latitude), float(stage_b.longitude),
        )
        fallback_speed_mps = 25 * 1000 / 3600  # 25 km/h -> m/s
        duration_s = distance_m / fallback_speed_mps
        route_info = RouteInfo(distance_m=distance_m, duration_s=duration_s)

    _segment_cache[cache_key] = (route_info, time.monotonic())
    return route_info


def remaining_road_distance(current_vehicle_coords, next_stage, destination_stage) -> RouteInfo:
    """
    Remaining distance + duration from the vehicle's current position to
    the passenger's destination stage, walking stage-by-stage along the
    route rather than a single straight shot to the destination.

    current_vehicle_coords: (latitude, longitude) tuple of the vehicle's
        last known GPS position.
    next_stage: the next Stage the vehicle hasn't reached yet.
    destination_stage: the passenger's selected destination Stage.

    Returns a combined RouteInfo. Call this when rendering the journey
    screen (or when the current stage changes), not on every GPS ping.
    """
    vehicle_lat, vehicle_lon = current_vehicle_coords

    # Leg 1: vehicle's current position -> next stage (straight-line is
    # fine here; it's a short hop, not worth an OSRM call).
    first_leg_m = haversine_distance_m(
        vehicle_lat, vehicle_lon, float(next_stage.latitude), float(next_stage.longitude)
    )
    fallback_speed_mps = 25 * 1000 / 3600
    total_distance_m = first_leg_m
    total_duration_s = first_leg_m / fallback_speed_mps

    # Leg 2+: walk stage-to-stage from next_stage to destination_stage,
    # summing OSRM-backed segment distances (with per-segment fallback).
    stage = next_stage
    while stage.id != destination_stage.id:
        following = stage.next_stage
        if following is None:
            # Destination isn't actually ahead on this route -- data
            # inconsistency; stop rather than loop forever.
            break
        segment = get_segment_road_distance(stage, following)
        total_distance_m += segment.distance_m
        total_duration_s += segment.duration_s
        stage = following

    return RouteInfo(distance_m=total_distance_m, duration_s=total_duration_s)


def get_route_polyline(origin, destination):
    """
    Get encoded polyline for a route from OSRM.
    
    Args:
        origin: (longitude, latitude) tuple
        destination: (longitude, latitude) tuple
    
    Returns:
        Encoded polyline string or None on failure
    """
    base_url = getattr(settings, "OSRM_BASE_URL", "http://127.0.0.1:5000/route/v1/driving")
    coords = f"{origin[0]},{origin[1]};{destination[0]},{destination[1]}"
    url = f"{base_url}/{coords}"
    params = {"overview": "full", "geometries": "polyline", "steps": "false"}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data.get("code") == "Ok" and data.get("routes"):
            return data["routes"][0]["geometry"]
    except Exception:
        pass
    return None


def along_track_position(vehicle_lat, vehicle_lon, stages):
    """
    Distance (metres) already travelled along the ordered stage line.

    Projects the vehicle onto each consecutive-stage segment (planar
    approximation in local metres — fine for the short hops between
    stages) and keeps the closest projection's along-track distance.
    Returns (along_m, total_m, perp_m). The perpendicular distance tells
    "waiting at the first stage" (perp ~ 0) apart from "still walking to
    the route start" (perp large, along clamped to 0). This gives stage
    completion a stable definition that does not flicker like a radius
    check: a vehicle sitting between two stages still has an unambiguous
    distance.
    """
    import math

    points = [(float(s.latitude), float(s.longitude)) for s in stages]
    if len(points) < 2:
        return 0.0, 0.0, 0.0

    kx = 111320 * math.cos(math.radians((points[0][0] + points[-1][0]) / 2))
    ky = 110540.0
    px = vehicle_lon * kx
    py = vehicle_lat * ky

    best_along = 0.0
    best_perp = float("inf")
    cumulative = 0.0
    for i in range(len(points) - 1):
        ax = points[i][1] * kx
        ay = points[i][0] * ky
        bx = points[i + 1][1] * kx
        by = points[i + 1][0] * ky
        seg = math.hypot(bx - ax, by - ay)
        dx, dy = bx - ax, by - ay
        if seg > 0:
            t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
            t = max(0.0, min(1.0, t))
            proj_x = ax + t * dx
            proj_y = ay + t * dy
            perp = math.hypot(px - proj_x, py - proj_y)
            if perp < best_perp:
                best_perp = perp
                best_along = cumulative + t * seg
        cumulative += seg
    return best_along, cumulative, best_perp
