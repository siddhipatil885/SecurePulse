"""Retry-safe timeout and notification worker building blocks."""
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.dispatch import DispatchRepository, OutboxRepository
from app.services.dispatch_service import DispatchService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeliveryResult:
    delivered: bool
    provider_message_id: str | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None


class NotificationProvider(Protocol):
    name: str
    async def deliver(self, destination: str, event_type: str, payload: dict[str, Any],
                      idempotency_key: str) -> DeliveryResult: ...


class RecordingFakeProvider:
    """Local sink for development and drills; never contacts a real recipient."""

    name = "recording-fake"

    def __init__(self, max_records: int = 1000) -> None:
        self.max_records = max_records
        self.records: list[dict[str, Any]] = []

    async def deliver(self, destination: str, event_type: str, payload: dict[str, Any],
                      idempotency_key: str) -> DeliveryResult:
        self.records.append({"destination": destination, "event_type": event_type,
                             "payload": payload, "idempotency_key": idempotency_key})
        del self.records[:-self.max_records]
        return DeliveryResult(delivered=True, provider_message_id=f"fake:{idempotency_key}")


class TimeoutEscalator:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def run_once(self, limit: int = 50) -> int:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session, session.begin():
            repository = DispatchRepository(session)
            offers = await repository.due_offers(now, limit)
            service = DispatchService(session)
            for offer in offers:
                await service.expire(offer_id=offer.id, actor_subject="system:timeout")
            return len(offers)


class NotificationDispatcher:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession],
                 provider: NotificationProvider, worker_id: str) -> None:
        self.session_factory, self.provider, self.worker_id = session_factory, provider, worker_id

    async def run_once(self, limit: int = 50) -> int:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session, session.begin():
            claimed = await OutboxRepository(session).claim_batch(self.worker_id, now, limit)
            jobs = [(row.id, row.destination or "", row.kind, row.payload, row.dedupe_key)
                    for row in claimed]
        for outbox_id, destination, event_type, payload, key in jobs:
            try:
                result = await self.provider.deliver(destination, event_type, payload, key)
            except Exception as error:
                logger.exception("Notification provider failed", extra={"outbox_id": outbox_id})
                result = DeliveryResult(delivered=False, error=type(error).__name__)
            async with self.session_factory() as session, session.begin():
                await OutboxRepository(session).record_attempt(outbox_id, provider=self.provider.name,
                    result="DELIVERED" if result.delivered else "FAILED", now=datetime.now(timezone.utc),
                    provider_reference=result.provider_message_id, error=result.error,
                    response_metadata=result.metadata)
        return len(jobs)
