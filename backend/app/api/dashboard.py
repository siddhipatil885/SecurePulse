"""Dashboard integration with the existing authentication principal."""

from fastapi import APIRouter, Depends, Response
from app.core.auth import Principal, require_scope

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/session")
async def session(response: Response, principal: Principal = Depends(require_scope("read"))) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return {"subject": principal.subject, "scopes": sorted(principal.scopes),
            "property_ids": sorted(principal.property_ids) if principal.property_ids is not None else None}
