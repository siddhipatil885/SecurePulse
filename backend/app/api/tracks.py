"""Read-only API for the current anonymous Frigate person tracks."""

from typing import Any

from fastapi import APIRouter, Depends

from app.core.auth import require_scope
from app.core.dependencies import get_person_tracker
from app.services.person_tracker import PersonTracker

router = APIRouter(
    prefix="/tracks",
    tags=["tracks"],
    dependencies=[Depends(require_scope("read"))],
)


@router.get("")
async def get_active_tracks(
    tracker: PersonTracker = Depends(get_person_tracker),
) -> dict[str, list[dict[str, Any]]]:
    """Return active and grace-period tracks grouped by backend camera ID."""
    return tracker.snapshot()
