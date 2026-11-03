"""Retry-safe timeout and notification worker building blocks."""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.dispatch import DispatchRepository, OutboxRepository


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


class TimeoutEscalator:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def run_once(self, limit: int = 50) -> int:
        now = datetime.now(timezone.utc)
        async with self.session_factory() as session, session.begin():
            repository = DispatchRepository(session)
            offers = await repository.due_offers(now, limit)
            for offer in offers:
                await repository.transition(offer, status="EXPIRED", now=now,
                    actor_subject="system:timeout", correlation_id=f"timeout:{offer.id}:{offer.version}",
                    reason="deadline elapsed")
                from app.models import NotificationOutbox
                session.add(NotificationOutbox(property_id=offer.property_id,
                    security_event_id=offer.security_event_id, kind="DISPATCH_ESCALATION_REQUIRED",
                    destination=f"property:{offer.property_id}:dispatchers",
                    payload={"assignment_id": offer.id, "incident_id": offer.security_event_id,
                             "reason": "offer_expired"},
                    dedupe_key=f"assignment:{offer.id}:escalation:{offer.version}", status="PENDING"))
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
        deliveries = [(outbox_id, await self.provider.deliver(destination, event_type, payload, key))
            for outbox_id, destination, event_type, payload, key in jobs]
        for outbox_id, result in deliveries:
            async with self.session_factory() as session, session.begin():
                await OutboxRepository(session).record_attempt(outbox_id, provider=self.provider.name,
                    result="DELIVERED" if result.delivered else "FAILED", now=datetime.now(timezone.utc),
                    provider_reference=result.provider_message_id, error=result.error,
                    response_metadata=result.metadata)
        return len(deliveries)
