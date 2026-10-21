"""Read-only API for the current anonymous Frigate person tracks."""

from typing import Any

from fastapi import APIRouter, Depends

from app.core.auth import Principal, require_scope
from app.core.dependencies import get_camera_service, get_person_tracker
from app.services.camera_service import CameraService
from app.services.person_tracker import PersonTracker

router = APIRouter(prefix="/tracks", tags=["tracks"])


@router.get("")
async def get_active_tracks(
    principal: Principal = Depends(require_scope("read")),
    tracker: PersonTracker = Depends(get_person_tracker),
    cameras: CameraService = Depends(get_camera_service),
) -> dict[str, list[dict[str, Any]]]:
    """Return active and grace-period tracks grouped by backend camera ID."""
    snapshot = tracker.snapshot()
    authorized = await cameras.list(property_ids=principal.property_ids)
    authorized_ids = {str(camera.id) for camera in authorized}
    return {camera_id: tracks for camera_id, tracks in snapshot.items() if camera_id in authorized_ids}
