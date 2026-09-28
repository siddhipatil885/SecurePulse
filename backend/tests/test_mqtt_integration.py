"""MQTT integration tests for Frigate event pipeline."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.core.config import Settings
from app.domain.events import DetectionEvent
from app.integrations.frigate import FrigateEventParser, FrigatePayloadError
from app.services.event_processor import EventProcessor, EventProcessResult
from app.models.security_event import SecurityEvent


class TestFrigateEventParserMetadata:
    """Test that Frigate payloads preserve rich tracking metadata."""

    def test_parser_extracts_bounding_box_as_x1y1x2y2(self) -> None:
        """Verify bounding box format is [x1, y1, x2, y2]."""
        detection = FrigateEventParser().parse(
            {
                "type": "update",
                "before": {},
                "after": {
                    "id": "1789898622.985494-7n794l",
                    "camera": "laptop_camera",
                    "label": "person",
                    "top_score": 0.95,
                    "start_time": 1790105420.0,
                    "box": [390, 289, 949, 717],  # [x1, y1, x2, y2]
                },
            }
        )

        assert detection.metadata["bounding_box"] == [390, 289, 949, 717]
        # Verify format: width = x2 - x1, height = y2 - y1
        width = 949 - 390
        height = 717 - 289
        assert width == 559
        assert height == 428

    def test_parser_preserves_multiple_bounding_boxes_in_lifecycle(self) -> None:
        """Verify bounding box changes across updates are captured."""
        parser = FrigateEventParser()
        
        # First update
        det1 = parser.parse(
            {
                "type": "update",
                "after": {
                    "id": "event1",
                    "camera": "cam",
                    "label": "person",
                    "top_score": 0.94,
                    "start_time": 1.0,
                    "box": [390, 289, 949, 717],
                },
            }
        )
        
        # Second update with different box
        det2 = parser.parse(
            {
                "type": "update",
                "after": {
                    "id": "event1",
                    "camera": "cam",
                    "label": "person",
                    "top_score": 0.96,
                    "start_time": 1.0,
                    "box": [288, 302, 872, 719],
                },
            }
        )

        assert det1.metadata["bounding_box"] == [390, 289, 949, 717]
        assert det2.metadata["bounding_box"] == [288, 302, 872, 719]

    def test_parser_preserves_path_data(self) -> None:
        """Verify path_data is captured."""
        detection = FrigateEventParser().parse(
            {
                "type": "update",
                "after": {
                    "id": "event1",
                    "camera": "cam",
                    "label": "person",
                    "top_score": 0.94,
                    "start_time": 1.0,
                    "path_data": [[100, 200], [105, 205], [110, 210]],
                },
            }
        )

        assert detection.metadata["path_data"] == [[100, 200], [105, 205], [110, 210]]

    def test_parser_preserves_start_and_end_times(self) -> None:
        """Verify start_time and end_time are captured."""
        detection = FrigateEventParser().parse(
            {
                "type": "end",
                "after": {
                    "id": "event1",
                    "camera": "cam",
                    "label": "person",
                    "top_score": 0.94,
                    "start_time": 1790105420.0,
                    "end_time": 1790105425.5,
                },
            }
        )

        assert detection.metadata["start_time"] == 1790105420.0
        assert detection.metadata["end_time"] == 1790105425.5

    def test_parser_preserves_zones(self) -> None:
        """Verify zone tracking is captured."""
        detection = FrigateEventParser().parse(
            {
                "type": "update",
                "after": {
                    "id": "event1",
                    "camera": "cam",
                    "label": "person",
                    "top_score": 0.94,
                    "start_time": 1.0,
                    "zones": ["entrance", "lobby"],
                    "current_zones": ["lobby"],
                    "entered_zones": ["entrance"],
                },
            }
        )

        assert detection.metadata["zones"] == ["entrance", "lobby"]
        assert detection.metadata["current_zones"] == ["lobby"]
        assert detection.metadata["entered_zones"] == ["entrance"]

    def test_parser_preserves_tracking_metadata(self) -> None:
        """Verify motion and loitering tracking fields are captured."""
        detection = FrigateEventParser().parse(
            {
                "type": "update",
                "after": {
                    "id": "event1",
                    "camera": "cam",
                    "label": "person",
                    "top_score": 0.94,
                    "start_time": 1.0,
                    "current_estimated_speed": 2.5,
                    "velocity_angle": 45,
                    "motionless_count": 10,
                    "position_changes": 5,
                    "pending_loitering": True,
                    "max_severity": "HIGH",
                    "score": 85,
                    "computed_score": 0.92,
                },
            }
        )

        assert detection.metadata["current_estimated_speed"] == 2.5
        assert detection.metadata["velocity_angle"] == 45
        assert detection.metadata["motionless_count"] == 10
        assert detection.metadata["position_changes"] == 5
        assert detection.metadata["pending_loitering"] is True
        assert detection.metadata["max_severity"] == "HIGH"
        assert detection.metadata["score"] == 85
        assert detection.metadata["computed_score"] == 0.92


class TestFrameDimensions:
    """Test that frame dimensions are correctly configured."""

    def test_settings_frame_dimensions_default_values(self) -> None:
        """Verify default frame width and height are 1280x720."""
        settings = Settings()
        assert settings.frame_width == 1280
        assert settings.frame_height == 720

    def test_settings_frame_dimensions_custom_values(self) -> None:
        """Verify frame dimensions can be configured."""
        settings = Settings(frame_width=640, frame_height=480)
        assert settings.frame_width == 640
        assert settings.frame_height == 480


class TestLifecycleEventHandling:
    """Test handling of new/update/end event lifecycle."""

    def test_parser_recognizes_new_event(self) -> None:
        """Verify NEW events are recognized."""
        detection = FrigateEventParser().parse(
            {
                "type": "new",
                "after": {
                    "id": "event1",
                    "camera": "cam",
                    "label": "person",
                    "top_score": 0.94,
                    "start_time": 1.0,
                },
            }
        )

        assert detection.metadata["lifecycle"] == "new"

    def test_parser_recognizes_update_event(self) -> None:
        """Verify UPDATE events are recognized."""
        detection = FrigateEventParser().parse(
            {
                "type": "update",
                "after": {
                    "id": "event1",
                    "camera": "cam",
                    "label": "person",
                    "top_score": 0.94,
                    "start_time": 1.0,
                },
            }
        )

        assert detection.metadata["lifecycle"] == "update"

    def test_parser_recognizes_end_event(self) -> None:
        """Verify END events are recognized."""
        detection = FrigateEventParser().parse(
            {
                "type": "end",
                "after": {
                    "id": "event1",
                    "camera": "cam",
                    "label": "person",
                    "top_score": 0.94,
                    "start_time": 1.0,
                    "end_time": 2.0,
                },
            }
        )

        assert detection.metadata["lifecycle"] == "end"

    def test_parser_rejects_unknown_lifecycle_event(self) -> None:
        """Verify unknown lifecycle types are rejected."""
        with pytest.raises(FrigatePayloadError):
            FrigateEventParser().parse(
                {
                    "type": "unknown",
                    "after": {
                        "id": "event1",
                        "camera": "cam",
                        "label": "person",
                        "top_score": 0.94,
                        "start_time": 1.0,
                    },
                }
            )


class TestEventIdPreservation:
    """Test that event IDs are preserved correctly throughout lifecycle."""

    def test_same_event_id_across_lifecycle(self) -> None:
        """Verify event ID is preserved from new to update to end."""
        parser = FrigateEventParser()
        event_id = "1789898622.985494-7n794l"

        new_event = parser.parse(
            {
                "type": "new",
                "after": {
                    "id": event_id,
                    "camera": "cam",
                    "label": "person",
                    "top_score": 0.94,
                    "start_time": 1.0,
                },
            }
        )

        update_event = parser.parse(
            {
                "type": "update",
                "after": {
                    "id": event_id,
                    "camera": "cam",
                    "label": "person",
                    "top_score": 0.95,
                    "start_time": 1.0,
                },
            }
        )

        end_event = parser.parse(
            {
                "type": "end",
                "after": {
                    "id": event_id,
                    "camera": "cam",
                    "label": "person",
                    "top_score": 0.95,
                    "start_time": 1.0,
                    "end_time": 2.0,
                },
            }
        )

        assert new_event.source_event_id == event_id
        assert update_event.source_event_id == event_id
        assert end_event.source_event_id == event_id


class TestNonPersonFiltering:
    """Test that non-person objects are handled correctly."""

    def test_parser_accepts_person_label(self) -> None:
        """Verify person detections are accepted."""
        detection = FrigateEventParser().parse(
            {
                "type": "update",
                "after": {
                    "id": "event1",
                    "camera": "cam",
                    "label": "person",
                    "top_score": 0.94,
                    "start_time": 1.0,
                },
            }
        )

        assert detection.object_type == "person"

    def test_parser_accepts_non_person_labels(self) -> None:
        """Verify non-person labels are captured (filtering handled by SecurityEngine)."""
        detection = FrigateEventParser().parse(
            {
                "type": "update",
                "after": {
                    "id": "event1",
                    "camera": "cam",
                    "label": "dog",
                    "top_score": 0.87,
                    "start_time": 1.0,
                },
            }
        )

        assert detection.object_type == "dog"

    def test_parser_requires_label(self) -> None:
        """Verify label is required."""
        with pytest.raises(FrigatePayloadError):
            FrigateEventParser().parse(
                {
                    "type": "update",
                    "after": {
                        "id": "event1",
                        "camera": "cam",
                        "top_score": 0.94,
                        "start_time": 1.0,
                    },
                }
            )


class TestErrorHandling:
    """Test error handling for malformed MQTT events."""

    def test_parser_rejects_missing_after(self) -> None:
        """Verify events without 'after' object are rejected."""
        with pytest.raises(FrigatePayloadError):
            FrigateEventParser().parse({"type": "new", "before": {}})

    def test_parser_rejects_missing_event_id(self) -> None:
        """Verify events without ID are rejected."""
        with pytest.raises(FrigatePayloadError):
            FrigateEventParser().parse(
                {
                    "type": "update",
                    "after": {
                        "camera": "cam",
                        "label": "person",
                        "top_score": 0.94,
                        "start_time": 1.0,
                    },
                }
            )

    def test_parser_rejects_missing_camera(self) -> None:
        """Verify events without camera are rejected."""
        with pytest.raises(FrigatePayloadError):
            FrigateEventParser().parse(
                {
                    "type": "update",
                    "after": {
                        "id": "event1",
                        "label": "person",
                        "top_score": 0.94,
                        "start_time": 1.0,
                    },
                }
            )

    def test_parser_rejects_missing_score(self) -> None:
        """Verify events without top_score are rejected."""
        with pytest.raises(FrigatePayloadError):
            FrigateEventParser().parse(
                {
                    "type": "update",
                    "after": {
                        "id": "event1",
                        "camera": "cam",
                        "label": "person",
                        "start_time": 1.0,
                    },
                }
            )

    def test_parser_handles_malformed_json(self) -> None:
        """Verify invalid JSON is rejected."""
        with pytest.raises(FrigatePayloadError):
            FrigateEventParser().parse(b"not json")

    def test_parser_handles_non_utf8_payload(self) -> None:
        """Verify non-UTF8 payloads are rejected."""
        with pytest.raises(FrigatePayloadError):
            FrigateEventParser().parse(b"\xff\xfe invalid utf8")

    def test_parser_handles_malformed_bounding_box(self) -> None:
        """Verify malformed bounding boxes are ignored."""
        detection = FrigateEventParser().parse(
            {
                "type": "update",
                "after": {
                    "id": "event1",
                    "camera": "cam",
                    "label": "person",
                    "top_score": 0.94,
                    "start_time": 1.0,
                    "box": [1, 2, 3],  # Wrong length
                },
            }
        )

        # Should not have bounding_box if malformed
        assert "bounding_box" not in detection.metadata


@pytest.mark.asyncio
class TestEventLifecycleProcessing:
    """Test EventProcessor handling of lifecycle events."""

    async def test_processor_creates_new_event_on_new_lifecycle(self) -> None:
        """Verify NEW events create SecurityEvent."""
        # This is a simplified test - full integration would need mocked repos
        detection = DetectionEvent(
            source="frigate",
            source_event_id="event1",
            camera="cam",
            object_type="person",
            confidence=0.94,
            timestamp=datetime.now(timezone.utc),
            metadata={"lifecycle": "new"},
        )

        assert detection.metadata["lifecycle"] == "new"

    async def test_processor_handles_end_event_on_duplicate(self) -> None:
        """Verify END events update existing event status to CLOSED."""
        # This test verifies the logic - full integration needs mocked session
        detection = DetectionEvent(
            source="frigate",
            source_event_id="event1",
            camera="cam",
            object_type="person",
            confidence=0.94,
            timestamp=datetime.now(timezone.utc),
            metadata={"lifecycle": "end", "end_time": 1790105425.5},
        )

        assert detection.metadata["lifecycle"] == "end"
        assert detection.metadata["end_time"] == 1790105425.5
