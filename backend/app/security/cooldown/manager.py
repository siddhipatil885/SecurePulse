"""
In-memory cooldown / deduplication manager.

Prevents the same security event from being emitted repeatedly within a
configurable time window.

Cooldown key:
    ``(camera_id, event_type, object_id)``

Example:
    First ``ZONE_ENTRY`` for cam1 / person-123 → allowed
    Second within 30 s → suppressed
    After 30 s → allowed again

NOTE — In-memory limitation
    Cooldown state lives in the process.  If the service restarts the
    cooldowns reset.  For production, consider Redis TTL keys.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

_CooldownKey = Tuple[str, str, str]  # (camera_id, event_type, object_id)


class CooldownManager:
    """TTL-based event deduplication.

    Args:
        default_ttl: Fallback cooldown in seconds when no per-event-type
            override is configured.
    """

    def __init__(self, default_ttl: float = 10.0) -> None:
        self._default_ttl = default_ttl
        # key → last_emitted_timestamp
        self._registry: Dict[_CooldownKey, datetime] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_allowed(
        self,
        camera_id: str,
        event_type: str,
        object_id: str,
        now: datetime,
        ttl: float | None = None,
    ) -> bool:
        """Return ``True`` if the event is **not** suppressed by cooldown.

        If allowed, the internal timestamp is updated so that the next
        call with the same key within *ttl* seconds returns ``False``.

        Args:
            camera_id: Camera that produced the event.
            event_type: Event type string (e.g. ``"ZONE_ENTRY"``).
            object_id: The detected object's tracking id.
            now: Current evaluation timestamp.
            ttl: Cooldown duration in seconds.  Falls back to
                ``default_ttl`` when ``None``.
        """
        cooldown = ttl if ttl is not None else self._default_ttl
        key: _CooldownKey = (camera_id, event_type, object_id)
        last = self._registry.get(key)

        if last is not None:
            elapsed = (now - last).total_seconds()
            if elapsed < cooldown:
                logger.debug(
                    "Event suppressed by cooldown: type=%s camera=%s "
                    "object=%s remaining=%.1fs",
                    event_type,
                    camera_id,
                    object_id,
                    cooldown - elapsed,
                )
                return False

        # Record or refresh the timestamp.
        self._registry[key] = now
        return True

    def reset(self) -> None:
        """Clear all cooldown state."""
        self._registry.clear()

    def remove_object(self, camera_id: str, object_id: str) -> None:
        """Remove all cooldown entries for an object that left the frame."""
        keys_to_remove = [
            k for k in self._registry
            if k[0] == camera_id and k[2] == object_id
        ]
        for k in keys_to_remove:
            del self._registry[k]
