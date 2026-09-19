"""Camera database access."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.camera import Camera


class CameraRepository:
    """Persist and retrieve camera records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, camera_id: int) -> Camera | None:
        return await self.session.get(Camera, camera_id)

    async def get_by_frigate_name(self, frigate_camera_name: str) -> Camera | None:
        statement = select(Camera).where(Camera.frigate_camera_name == frigate_camera_name)
        return await self.session.scalar(statement)

    async def list(self, enabled: bool | None = None) -> list[Camera]:
        statement = select(Camera).order_by(Camera.id)
        if enabled is not None:
            statement = statement.where(Camera.enabled == enabled)
        return list((await self.session.scalars(statement)).all())