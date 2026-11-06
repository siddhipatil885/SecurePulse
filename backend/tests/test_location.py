from app.services.location import distance_metres, estimate_eta_seconds


def test_distance_and_eta_are_bounded_and_deterministic():
    distance = distance_metres(18.5204, 73.8567, 18.5304, 73.8567)
    assert 1000 < distance < 1200
    assert estimate_eta_seconds(distance, 10) == round(distance / 10)


def test_eta_uses_safe_fallback_when_speed_is_missing_or_stationary():
    assert estimate_eta_seconds(800, None) == 100
    assert estimate_eta_seconds(800, 0) == 100
