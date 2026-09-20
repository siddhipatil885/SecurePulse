"""Camera read endpoints."""

from fastapi import APIRouter, Depends, Query

from app.core.auth import require_scope
from app.core.dependencies import get_camera_service
from app.schemas.camera import CameraResponse
from app.services.camera_service import CameraService

router = APIRouter(
    prefix="/cameras", tags=["cameras"], dependencies=[Depends(require_scope("read"))]
)


@router.get("", response_model=list[CameraResponse], summary="List cameras")
async def list_cameras(
    enabled: bool | None = Query(default=None),
    service: CameraService = Depends(get_camera_service),
) -> list[CameraResponse]:
    return await service.list(enabled=enabled)


@router.get("/{camera_id}", response_model=CameraResponse, summary="Get a camera")
async def get_camera(
    camera_id: int,
    service: CameraService = Depends(get_camera_service),
) -> CameraResponse:
    return await service.get(camera_id)