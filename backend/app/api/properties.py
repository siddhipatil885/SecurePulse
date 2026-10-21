"""Authorized property discovery endpoints."""

from fastapi import APIRouter, Depends

from app.core.auth import Principal, require_scope
from app.core.dependencies import get_property_service
from app.schemas.property import PropertyResponse
from app.services.property_service import PropertyService

router = APIRouter(prefix="/properties", tags=["properties"])


@router.get("", response_model=list[PropertyResponse])
async def list_properties(
    principal: Principal = Depends(require_scope("read")),
    service: PropertyService = Depends(get_property_service),
) -> list[PropertyResponse]:
    return await service.list(principal.property_ids)
