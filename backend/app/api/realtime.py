"""WebSocket real-time event stream."""

import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.core.auth import Principal, get_websocket_principal, authenticate_token, websocket_token
from app.core.config import get_settings
from app.core.exceptions import ApplicationError
from app.core.dependencies import get_event_publisher
from app.realtime.publisher import InMemoryEventPublisher

router = APIRouter(prefix="/events", tags=["realtime"])


@router.websocket("/stream")
async def event_stream(
    websocket: WebSocket,
    principal: Principal = Depends(get_websocket_principal),
) -> None:
    """Stream committed security events to a connected dashboard client."""

    origin = websocket.headers.get("origin")
    if origin and origin.rstrip("/") not in get_settings().parsed_cors_origins:
        await websocket.close(code=1008)
        return
    publisher = get_event_publisher()
    try:
        queue = await publisher.subscribe(principal.property_ids)
    except OverflowError:
        await websocket.close(code=1013)
        return
    try:
        protocols = websocket.headers.get("sec-websocket-protocol", "").split(",")
        await websocket.accept(subprotocol="securepulse.v1" if "securepulse.v1" in [p.strip() for p in protocols] else None)
        await websocket.send_json({"version": 1, "type": "resync_required"})
        while True:
            try:
                message = await asyncio.wait_for(queue.get(), timeout=15)
            except asyncio.TimeoutError:
                message = {"version": 1, "type": "heartbeat"}
            # Recheck expiry even on quiet connections and before every send.
            try:
                current = authenticate_token(websocket_token(websocket))
                if "read" not in current.scopes or current.property_ids != principal.property_ids:
                    raise ApplicationError("FORBIDDEN", "Session permissions changed", 403)
            except ApplicationError:
                await websocket.close(code=4401, reason="Session expired; sign in again")
                break
            await asyncio.wait_for(websocket.send_json(message), timeout=10)
    except (WebSocketDisconnect, asyncio.CancelledError, asyncio.TimeoutError):
        pass
    finally:
        await publisher.unsubscribe(queue)
