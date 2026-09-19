"""Phase 5 security-engine contract tests."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.domain.security import SecurityContext, SecurityDecision


def test_security_decision_accepts_valid_result() -> None:
    decision = SecurityDecision(
        event_type="PERSON_DETECTED",
        score=15,
        severity="INFO",
        reason="Person detected",
    )

    assert decision.score == 15
    assert decision.severity == "INFO"


@pytest.mark.parametrize("score", [-1, 101])
def test_security_decision_rejects_invalid_score(score: int) -> None:
    with pytest.raises(ValidationError):
        SecurityDecision(event_type="PERSON_DETECTED", score=score, severity="INFO")


def test_security_context_is_typed() -> None:
    context = SecurityContext(
        camera_id=1,
        object_type="person",
        confidence=0.94,
        timestamp=datetime(2026, 9, 19, tzinfo=timezone.utc),
        zone=None,
    )

    assert context.camera_id == 1