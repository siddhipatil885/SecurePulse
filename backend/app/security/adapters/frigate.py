"""
Frigate to Security Engine Adapter.

Converts raw Frigate event JSON payloads into the SecurityEngine's
internal ``DetectionEvent`` model.

Mappings:
    Frigate id           -> source_event_id
    Frigate camera       -> camera_id
    Frigate label        -> object_type
    Frigate data.score   -> confidence
    Frigate start_time   -> timestamp
    Frigate data.box     -> bbox
    Frigate end_time     -> event_state

Assumptions:
    1. Object Identity: The Frigate event ``id`` is assumed to track a single
       unique object for its lifetime, thus mapped directly to ``object_id``.
       Limitation: If Frigate drops a track and assigns a new ID to the same
       physical person, the SecurityEngine will treat them as two distinct people.
    2. Coordinate Ordering: Frigate data.box uses ``[x1, y1, x2, y2]``.
       If coordinates are > 1, they are treated as absolute pixels. If they are
       <= 1, they are treated as normalized and multiplied by frame dimensions.
    3. Normalization: The SecurityEngine expects ``BoundingBox`` to be in pixel
       space. If normalized coords are provided without frame dimensions, ``bbox``
       is set to ``None``. Validation ensures x2 >= x1 and y2 >= y1.
    4. Identity: Multiple consecutive updates with the same Frigate ID will
       produce identical ``object_id`` values, preserving identity across updates.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.security.models import BoundingBox, DetectionEvent, EventState


class FrigateDetectionAdapter:
    """Normalizes raw Frigate events into Security Intelligence detection events."""

    @staticmethod
    def parse(
        payload: Dict[str, Any],
        frame_width: Optional[int] = None,
        frame_height: Optional[int] = None,
    ) -> DetectionEvent:
        """Parse a raw Frigate event payload into a DetectionEvent.

        Args:
            payload: The raw Frigate JSON event payload.
            frame_width: Optional width of the camera frame in pixels.
            frame_height: Optional height of the camera frame in pixels.

        Returns:
            A normalized DetectionEvent ready for the SecurityEngine.
        """
        # Handle MQTT event structure: payload may have "after" key
        if "after" in payload and isinstance(payload["after"], dict):
            # Extract lifecycle from MQTT type if available
            mqtt_type = payload.get("type", "update")
            data_source = payload["after"]
        else:
            mqtt_type = "update"
            data_source = payload

        source_event_id = data_source["id"]
        
        # Assumption 1: Frigate ID serves as a unique object tracking ID
        object_id = source_event_id

        # Lifecycle state
        # end_time is null when the event is ongoing
        end_time = data_source.get("end_time")
        if end_time is not None:
            event_state = EventState.END
        elif mqtt_type == "new":
            event_state = EventState.START
        else:
            event_state = EventState.UPDATE

        # Use frame_time for the most accurate current detection time, fallback to start_time
        time_val = data_source.get("frame_time", data_source.get("start_time"))
        timestamp = datetime.fromtimestamp(time_val, tz=timezone.utc)

        # Coordinate processing
        bbox = None
        raw_box = data_source.get("box")
        if raw_box and len(raw_box) == 4:
            # Format is [x1, y1, x2, y2]
            val_x1, val_y1, val_x2, val_y2 = raw_box
            
            if val_x2 >= val_x1 and val_y2 >= val_y1:
                # If values are > 1, assume they are absolute pixels already
                if val_x2 > 1.0 or val_y2 > 1.0:
                    x1 = float(val_x1)
                    y1 = float(val_y1)
                    x2 = float(val_x2)
                    y2 = float(val_y2)
                    bbox = BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2)
                elif frame_width and frame_height:
                    # Normalized coords, scale them
                    x1 = val_x1 * frame_width
                    y1 = val_y1 * frame_height
                    x2 = val_x2 * frame_width
                    y2 = val_y2 * frame_height
                    bbox = BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2)

        return DetectionEvent(
            source="frigate",
            source_event_id=source_event_id,
            camera_id=data_source["camera"],
            object_id=object_id,
            object_type=data_source["label"],
            confidence=data_source.get("score", 0.0),
            timestamp=timestamp,
            bbox=bbox,
            frame_width=frame_width,
            frame_height=frame_height,
            event_state=event_state,
            metadata={"raw_frigate_event": payload, "path_data": data_source.get("path_data", [])},
        )
