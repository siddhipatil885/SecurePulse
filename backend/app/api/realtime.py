"""WebSocket real-time event stream."""

import asyncio

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.core.auth import Principal, get_websocket_principal
from app.core.dependencies import get_event_publisher
from app.realtime.publisher import InMemoryEventPublisher

router = APIRouter(prefix="/events", tags=["realtime"])


@router.websocket("/stream")
async def event_stream(
    websocket: WebSocket,
    _: Principal = Depends(get_websocket_principal),
) -> None:
    """Stream committed security events to a connected dashboard client."""

    await websocket.accept()
    publisher = get_event_publisher()
    queue = await publisher.subscribe()
    try:
        while True:
            await websocket.send_json(await queue.get())
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        await publisher.unsubscribe(queue)