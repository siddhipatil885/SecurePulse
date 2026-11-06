"""Privacy-preserving, provider-independent location calculations."""

from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_M = 6_371_000
DEFAULT_URBAN_SPEED_MPS = 8.0
MIN_MOVING_SPEED_MPS = 1.0


def distance_metres(
    latitude: float, longitude: float, target_latitude: float, target_longitude: float
) -> float:
    """Return a great-circle distance for short-range ETA estimates."""
    lat1, lat2 = radians(latitude), radians(target_latitude)
    delta_lat = lat2 - lat1
    delta_lon = radians(target_longitude - longitude)
    value = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    return 2 * EARTH_RADIUS_M * asin(sqrt(min(1.0, value)))


def estimate_eta_seconds(distance_m: float, speed_mps: float | None) -> int:
    """Estimate arrival using current speed or a conservative urban fallback."""
    speed = speed_mps if speed_mps is not None and speed_mps >= MIN_MOVING_SPEED_MPS else DEFAULT_URBAN_SPEED_MPS
    return max(0, round(distance_m / speed))
