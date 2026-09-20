"""Frigate MQTT adapter and payload parser."""

import json
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import paho.mqtt.client as mqtt
from paho.mqtt import MQTTException
from paho.mqtt.client import MQTTMessage

from app.core.config import Settings, get_settings
from app.domain.events import DetectionEvent

logger = logging.getLogger(__name__)


class FrigatePayloadError(ValueError):
    """Raised when a Frigate event cannot be normalized."""


class FrigateEventParser:
    """Convert Frigate MQTT event payloads into internal detection events."""

    _supported_lifecycle_events = {"new", "update", "end"}

    def parse(self, payload: bytes | str | dict[str, Any]) -> DetectionEvent:
        data = self._decode_payload(payload)
        lifecycle = data.get("type")
        if lifecycle not in self._supported_lifecycle_events:
            raise FrigatePayloadError("unsupported Frigate event type")

        event = data.get("after")
        if not isinstance(event, dict):
            raise FrigatePayloadError("Frigate event is missing an after object")

        source_event_id = self._required_string(event, "id")
        camera = self._required_string(event, "camera")
        object_type = self._required_string(event, "label")
        confidence = event.get("top_score")
        if not isinstance(confidence, (int, float)):
            raise FrigatePayloadError("Frigate event has no numeric top_score")

        timestamp = self._parse_timestamp(event.get("start_time", event.get("timestamp")))
        return DetectionEvent(
            source="frigate",
            source_event_id=source_event_id,
            camera=camera,
            object_type=object_type,
            confidence=confidence,
            timestamp=timestamp,
            metadata={
                "lifecycle": lifecycle,
                "zones": event.get("zones", []),
                "has_snapshot": bool(event.get("has_snapshot", False)),
                "has_clip": bool(event.get("has_clip", False)),
            },
        )

    @staticmethod
    def _decode_payload(payload: bytes | str | dict[str, Any]) -> dict[str, Any]:
        if isinstance(payload, bytes):
            try:
                payload = payload.decode("utf-8")
            except UnicodeDecodeError as error:
                raise FrigatePayloadError("Frigate payload is not valid UTF-8") from error
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as error:
                raise FrigatePayloadError("Frigate payload is not valid JSON") from error
        if not isinstance(payload, dict):
            raise FrigatePayloadError("Frigate payload must be a JSON object")
        return payload

    @staticmethod
    def _required_string(event: dict[str, Any], key: str) -> str:
        value = event.get(key)
        if not isinstance(value, str) or not value.strip():
            raise FrigatePayloadError(f"Frigate event is missing {key}")
        return value.strip()

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as error:
                raise FrigatePayloadError("Frigate timestamp is invalid") from error
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        raise FrigatePayloadError("Frigate event has no valid timestamp")


class FrigateClient:
    """Resilient MQTT client that delivers normalized Frigate detections."""

    def __init__(
        self,
        on_detection: Callable[[DetectionEvent], None],
        settings: Settings | None = None,
        parser: FrigateEventParser | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.on_detection = on_detection
        self.parser = parser or FrigateEventParser()
        self.client = mqtt.Client(client_id=self.settings.mqtt_client_id)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(
            min_delay=self.settings.mqtt_reconnect_min_delay,
            max_delay=self.settings.mqtt_reconnect_max_delay,
        )
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def start(self) -> bool:
        """Start the background MQTT loop; return false if initial connection fails."""

        try:
            self.client.connect(
                self.settings.mqtt_host,
                self.settings.mqtt_port,
                keepalive=60,
            )
            self.client.loop_start()
            return True
        except (OSError, MQTTException) as error:
            logger.warning("Unable to connect to Frigate MQTT", extra={"error": str(error)})
            return False

    def stop(self) -> None:
        """Stop the MQTT loop and disconnect cleanly."""

        self.client.loop_stop()
        if self._connected:
            self.client.disconnect()
        self._connected = False

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: dict[str, Any], rc: int) -> None:
        if rc == 0:
            self._connected = True
            client.subscribe(self.settings.frigate_mqtt_topic, qos=0)
            logger.info("Connected to Frigate MQTT")
        else:
            logger.warning("Frigate MQTT connection rejected", extra={"result_code": rc})

    def _on_disconnect(
        self, client: mqtt.Client, userdata: Any, rc: int
    ) -> None:
        self._connected = False
        if rc != 0:
            logger.warning("Disconnected from Frigate MQTT", extra={"result_code": rc})

    def _on_message(self, client: mqtt.Client, userdata: Any, message: MQTTMessage) -> None:
        try:
            detection = self.parser.parse(message.payload)
            self.on_detection(detection)
        except (FrigatePayloadError, ValueError) as error:
            logger.warning("Rejected malformed Frigate event", extra={"error": str(error)})
        except Exception:
            logger.exception("Failed to deliver Frigate detection")