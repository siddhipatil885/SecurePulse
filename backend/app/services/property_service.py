"""Authorized property discovery service."""

from app.models.tenancy import Property
from app.repositories.properties import PropertyRepository


class PropertyService:
    def __init__(self, repository: PropertyRepository) -> None:
        self.repository = repository

    async def list(self, property_ids: frozenset[int] | None) -> list[Property]:
        return await self.repository.list_authorized(property_ids)
