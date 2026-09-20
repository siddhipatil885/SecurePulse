"""Lifecycle wrapper for the Frigate MQTT adapter."""

from collections.abc import Callable

from app.core.config import Settings
from app.domain.events import DetectionEvent
from app.integrations.frigate import FrigateClient


class FrigateListener:
    """Own the adapter lifecycle without putting MQTT logic in the API layer."""

    def __init__(
        self, on_detection: Callable[[DetectionEvent], None], settings: Settings | None = None
    ) -> None:
        self.client = FrigateClient(on_detection=on_detection, settings=settings)

    def start(self) -> bool:
        return self.client.start()

    def stop(self) -> None:
        self.client.stop()