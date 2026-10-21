"""Camera database access."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.camera import Camera
from app.models.camera_operations import CameraHealthObservation


class CameraRepository:
    """Persist and retrieve camera records."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _with_latest_health(statement):
        status = (
            select(CameraHealthObservation.status)
            .where(CameraHealthObservation.camera_id == Camera.id)
            .order_by(CameraHealthObservation.observed_at.desc(), CameraHealthObservation.id.desc())
            .limit(1)
            .correlate(Camera)
            .scalar_subquery()
        )
        observed_at = (
            select(CameraHealthObservation.observed_at)
            .where(CameraHealthObservation.camera_id == Camera.id)
            .order_by(CameraHealthObservation.observed_at.desc(), CameraHealthObservation.id.desc())
            .limit(1)
            .correlate(Camera)
            .scalar_subquery()
        )
        return statement.add_columns(
            status.label("health_status"), observed_at.label("health_observed_at")
        )

    @staticmethod
    def _attach_health(row) -> Camera:
        camera, health_status, health_observed_at = row
        camera.health_status = health_status
        camera.health_observed_at = health_observed_at
        return camera

    async def get_by_id(
        self, camera_id: int, property_ids: frozenset[int] | None = None
    ) -> Camera | None:
        statement = select(Camera).where(Camera.id == camera_id)
        if property_ids is not None:
            statement = statement.where(Camera.property_id.in_(property_ids))
        row = (await self.session.execute(self._with_latest_health(statement))).one_or_none()
        return self._attach_health(row) if row else None

    async def get_by_frigate_name(self, frigate_camera_name: str) -> Camera | None:
        statement = select(Camera).where(Camera.frigate_camera_name == frigate_camera_name)
        return await self.session.scalar(statement)

    async def get_authorized_by_frigate_name(
        self, frigate_camera_name: str, property_ids: frozenset[int] | None
    ) -> Camera | None:
        statement = select(Camera).where(Camera.frigate_camera_name == frigate_camera_name)
        if property_ids is not None:
            statement = statement.where(Camera.property_id.in_(property_ids))
        row = (await self.session.execute(self._with_latest_health(statement))).one_or_none()
        return self._attach_health(row) if row else None

    async def list(
        self,
        enabled: bool | None = None,
        property_ids: frozenset[int] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Camera]:
        statement = select(Camera).order_by(Camera.id)
        if property_ids is not None:
            statement = statement.where(Camera.property_id.in_(property_ids))
        if enabled is not None:
            statement = statement.where(Camera.enabled == enabled)
        statement = statement.offset(offset)
        if limit is not None:
            statement = statement.limit(limit)
        rows = (await self.session.execute(self._with_latest_health(statement))).all()
        return [self._attach_health(row) for row in rows]
