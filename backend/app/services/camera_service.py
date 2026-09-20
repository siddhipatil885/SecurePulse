"""Camera application service."""

from app.core.exceptions import ApplicationError
from app.models.camera import Camera
from app.repositories.cameras import CameraRepository


class CameraService:
    """Coordinate camera reads without exposing repository details to routes."""

    def __init__(self, repository: CameraRepository) -> None:
        self.repository = repository

    async def list(self, enabled: bool | None = None) -> list[Camera]:
        return await self.repository.list(enabled=enabled)

    async def get(self, camera_id: int) -> Camera:
        camera = await self.repository.get_by_id(camera_id)
        if camera is None:
            raise ApplicationError(
                "CAMERA_NOT_FOUND", "The requested camera does not exist.", 404
            )
        return camera