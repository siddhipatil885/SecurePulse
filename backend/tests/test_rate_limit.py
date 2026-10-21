"""Mutation rate-limit behavior."""

import pytest

from app.core.rate_limit import SlidingWindowRateLimiter


@pytest.mark.anyio
async def test_rate_limiter_is_scoped_by_subject_and_recovers_after_window() -> None:
    now = 100.0
    limiter = SlidingWindowRateLimiter(2, window_seconds=10, clock=lambda: now)

    assert await limiter.check("operator-a") is None
    assert await limiter.check("operator-a") is None
    assert await limiter.check("operator-a") == 10
    assert await limiter.check("operator-b") is None

    now = 111.0
    assert await limiter.check("operator-a") is None
