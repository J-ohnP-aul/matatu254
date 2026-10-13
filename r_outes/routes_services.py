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

# How close (meters) the vehicle must be to a stage to count as "reached".
# MVP constant for now; move to system_config once the admin threshold
# screens (FR-A-07) exist.
STAGE_ARRIVAL_RADIUS_M = 20


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
    origin = (float(stage_a.longitude), float(stage_a.latitude))
    destination = (float(stage_b.longitude), float(stage_b.latitude))

    try:
        return get_route_info(origin, destination)
    except OSRMError:
        # Fallback: straight-line distance, assume a flat average speed
        # (25 km/h) to still produce a usable duration estimate.
        distance_m = haversine_distance_m(
            float(stage_a.latitude), float(stage_a.longitude),
            float(stage_b.latitude), float(stage_b.longitude),
        )
        fallback_speed_mps = 25 * 1000 / 3600  # 25 km/h -> m/s
        duration_s = distance_m / fallback_speed_mps
        return RouteInfo(distance_m=distance_m, duration_s=duration_s)


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
