"""WebSocket real-time event stream."""

import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.core.auth import Principal, get_websocket_principal
from app.core.dependencies import get_event_publisher
from app.database.database import get_session_factory
from app.api.dispatch import can_view_assignment_location
from app.realtime.publisher import InMemoryEventPublisher

router = APIRouter(prefix="/events", tags=["realtime"])


@router.websocket("/stream")
async def event_stream(
    websocket: WebSocket,
    principal: Principal = Depends(get_websocket_principal),
) -> None:
    """Stream committed security events to a connected dashboard client."""

    await websocket.accept()
    publisher = get_event_publisher()
    async def authorize_location(property_id, assignment_id):
        async with get_session_factory()() as session:
            return await can_view_assignment_location(principal, property_id, assignment_id, session)
    queue = await publisher.subscribe(principal.property_ids, location_access=authorize_location)
    try:
        while True:
            message = await queue.get()
            if message.get('type') == 'marshal_location' and not await authorize_location(message['property_id'], message['data']['assignment_id']):
                continue
            await websocket.send_json(message)
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        await publisher.unsubscribe(queue)
