"""Camera read endpoints."""

from fastapi import APIRouter, Depends, Query

from app.core.auth import Principal, require_scope
from app.core.dependencies import get_camera_service
from app.schemas.camera import CameraResponse
from app.services.camera_service import CameraService

router = APIRouter(prefix="/cameras", tags=["cameras"])


@router.get("", response_model=list[CameraResponse], summary="List cameras")
async def list_cameras(
    enabled: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    principal: Principal = Depends(require_scope("read")),
    service: CameraService = Depends(get_camera_service),
) -> list[CameraResponse]:
    return await service.list(enabled=enabled, property_ids=principal.property_ids,
                              limit=page_size, offset=(page - 1) * page_size)


@router.get("/{camera_id}", response_model=CameraResponse, summary="Get a camera")
async def get_camera(
    camera_id: int,
    principal: Principal = Depends(require_scope("read")),
    service: CameraService = Depends(get_camera_service),
) -> CameraResponse:
    return await service.get(camera_id, property_ids=principal.property_ids)
