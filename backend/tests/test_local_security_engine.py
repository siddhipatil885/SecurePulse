"""Integration coverage for the in-process security-engine adapter."""

from datetime import datetime, timezone

import pytest

from app.domain.security import SecurityContext
from app.integrations.local_security_engine import LocalSecurityEngine
from app.security.config import SecurityConfig
from app.security.engine import SecurityEngine
from app.security.models import Point, Zone


@pytest.mark.asyncio
async def test_local_engine_converts_normalized_track_box_to_zone_pixels() -> None:
    engine = LocalSecurityEngine(
        SecurityEngine(
            SecurityConfig(
                zones=[
                    Zone(
                        id="restricted",
                        name="Restricted",
                        camera_id="1",
                        polygon=[
                            Point(x=100, y=400),
                            Point(x=500, y=400),
                            Point(x=500, y=700),
                            Point(x=100, y=700),
                        ],
                    )
                ]
            )
        )
    )

    decision = await engine.evaluate(
        SecurityContext(
            camera_id=1,
            object_type="person",
            confidence=0.9,
            timestamp=datetime(2026, 9, 19, tzinfo=timezone.utc),
            track_id="person_track_1",
            bounding_box={"x": 0.1, "y": 0.1, "width": 0.3, "height": 0.8},
            frame_width=1280,
            frame_height=720,
            active_person_count=1,
        )
    )

    assert decision.event_type == "ZONE_ENTRY"


@pytest.mark.asyncio
async def test_plain_person_detection_is_informational_not_an_incident() -> None:
    engine = LocalSecurityEngine(SecurityEngine(SecurityConfig(policy_version="pilot-1")))

    decision = await engine.evaluate(
        SecurityContext(
            camera_id=1,
            object_type="person",
            confidence=0.9,
            timestamp=datetime(2026, 9, 19, tzinfo=timezone.utc),
            track_id="person_track_2",
        )
    )

    assert decision.event_type == "DETECTION"
    assert decision.severity == "INFO"
    assert decision.metadata["policy_version"] == "pilot-1"


@pytest.mark.asyncio
async def test_candidate_evidence_references_reach_backend_decision() -> None:
    engine = LocalSecurityEngine(SecurityEngine(SecurityConfig()))
    decision = await engine.evaluate(
        SecurityContext(
            camera_id=1,
            object_type="person",
            confidence=0.9,
            timestamp=datetime(2026, 9, 19, tzinfo=timezone.utc),
            evidence_refs=["frigate:event-1:snapshot"],
        )
    )

    assert decision.metadata["evidence_refs"] == ["frigate:event-1:snapshot"]
