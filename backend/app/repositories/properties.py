"""Property database access constrained by authenticated tenant claims."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenancy import Property


class PropertyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_authorized(
        self, property_ids: frozenset[int] | None
    ) -> list[Property]:
        statement = select(Property).where(Property.active.is_(True)).order_by(Property.name)
        if property_ids is not None:
            statement = statement.where(Property.id.in_(property_ids))
        return list((await self.session.scalars(statement)).all())
