"""Camera application service."""

from app.core.exceptions import ApplicationError
from app.models.camera import Camera
from app.repositories.cameras import CameraRepository


class CameraService:
    """Coordinate camera reads without exposing repository details to routes."""

    def __init__(self, repository: CameraRepository) -> None:
        self.repository = repository

    async def list(
        self, enabled: bool | None = None, property_ids: frozenset[int] | None = None,
        limit: int | None = None, offset: int = 0,
    ) -> list[Camera]:
        return await self.repository.list(enabled=enabled, property_ids=property_ids, limit=limit, offset=offset)

    async def get(
        self, camera_id: int, property_ids: frozenset[int] | None = None
    ) -> Camera:
        camera = await self.repository.get_by_id(camera_id, property_ids=property_ids)
        if camera is None:
            raise ApplicationError(
                "CAMERA_NOT_FOUND", "The requested camera does not exist.", 404
            )
        return camera

    async def get_by_frigate_name(
        self, camera_name: str, property_ids: frozenset[int] | None = None
    ) -> Camera:
        camera = await self.repository.get_authorized_by_frigate_name(camera_name, property_ids)
        if camera is None:
            raise ApplicationError("CAMERA_NOT_FOUND", "The requested camera does not exist.", 404)
        return camera
