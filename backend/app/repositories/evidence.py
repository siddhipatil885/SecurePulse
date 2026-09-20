"""Evidence metadata database access."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.evidence import Evidence


class EvidenceRepository:
    """Persist and retrieve evidence metadata without exposing filesystem contents."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, evidence: Evidence) -> Evidence:
        self.session.add(evidence)
        await self.session.flush()
        return evidence

    async def list_by_event(self, event_id: int) -> list[Evidence]:
        statement = select(Evidence).where(Evidence.event_id == event_id).order_by(Evidence.timestamp)
        return list((await self.session.scalars(statement)).all())