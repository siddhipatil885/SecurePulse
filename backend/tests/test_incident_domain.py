"""Engineer 2 tenant isolation and incident transaction tests."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import ApplicationError
from app.models.operations import IncidentStatusHistory, NotificationOutbox, SourceEventReceipt
from app.models.security_event import SecurityEvent
from app.services.incident_service import IncidentService


@pytest.mark.asyncio
async def test_legal_incident_command_is_audited_and_committed() -> None:
    incident = SecurityEvent(id=10, property_id=1, status="OPEN")
    repository = AsyncMock()
    repository.get_for_update.return_value = incident
    async def apply_transition(target: SecurityEvent, **values: object) -> None:
        target.status = str(values["new_status"])
    repository.record_transition.side_effect = apply_transition
    service = IncidentService(repository)

    result = await service.command(
        10,
        "acknowledge",
        actor_subject="operator-1",
        property_ids=frozenset({1}),
        reason="Reviewed camera evidence",
        correlation_id="request-123",
    )

    assert result.status == "ACKNOWLEDGED"
    repository.record_transition.assert_awaited_once_with(
        incident,
        new_status="ACKNOWLEDGED",
        actor_subject="operator-1",
        reason="Reviewed camera evidence",
        correlation_id="request-123",
    )


@pytest.mark.asyncio
async def test_illegal_incident_command_returns_conflict_without_write() -> None:
    repository = AsyncMock()
    repository.get_for_update.return_value = SecurityEvent(id=10, property_id=1, status="RESOLVED")
    service = IncidentService(repository)

    with pytest.raises(ApplicationError) as error:
        await service.command(
            10,
            "acknowledge",
            actor_subject="operator-1",
            property_ids=frozenset({1}),
            reason="late command",
            correlation_id="request-124",
        )

    assert error.value.code == "INVALID_INCIDENT_TRANSITION"
    assert error.value.status_code == 409
    repository.record_transition.assert_not_awaited()


@pytest.mark.asyncio
async def test_evidence_catalog_access_is_audited() -> None:
    incident = SecurityEvent(id=10, property_id=1, status="OPEN")
    repository = AsyncMock()
    repository.list_evidence.return_value = []
    repository.get.return_value = incident
    service = IncidentService(repository)

    result = await service.evidence(
        10,
        frozenset({1}),
        actor_subject="operator-1",
        correlation_id="request-evidence-1",
    )

    assert result == []
    repository.audit_evidence_access.assert_awaited_once_with(
        incident,
        actor_subject="operator-1",
        correlation_id="request-evidence-1",
    )


def test_new_operational_models_have_required_identity_constraints() -> None:
    receipt_constraints = {constraint.name for constraint in SourceEventReceipt.__table__.constraints}
    outbox_constraints = {constraint.name for constraint in NotificationOutbox.__table__.constraints}

    assert "uq_source_event_receipts_identity" in receipt_constraints
    assert "uq_notification_outbox_dedupe_key" in outbox_constraints
    assert IncidentStatusHistory.__table__.c.correlation_id.nullable is False
