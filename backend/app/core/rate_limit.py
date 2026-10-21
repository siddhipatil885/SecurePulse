"""Small process-local limiter for authenticated mutation commands."""

import asyncio
from collections import defaultdict, deque
from time import monotonic
from typing import Callable


class SlidingWindowRateLimiter:
    """Limit each key to a fixed number of calls during a rolling window.

    This protects a single API process. Multi-instance production deployments
    should additionally enforce a shared limit at the gateway.
    """

    def __init__(
        self,
        limit: int,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if limit < 1 or window_seconds <= 0:
            raise ValueError("Rate-limit values must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self.clock = clock
        self._calls: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str) -> int | None:
        """Record an allowed call, or return whole seconds until retry."""

        now = self.clock()
        cutoff = now - self.window_seconds
        async with self._lock:
            # Discard expired subjects as well as expired calls for this subject.
            for stale in [subject for subject, times in self._calls.items() if not times or times[-1] <= cutoff]:
                del self._calls[stale]
            calls = self._calls[key]
            while calls and calls[0] <= cutoff:
                calls.popleft()
            if len(calls) >= self.limit:
                remaining = max(1, int(self.window_seconds - (now - calls[0]) + 0.999))
                return remaining
            calls.append(now)
            return None
