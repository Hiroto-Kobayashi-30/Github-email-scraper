"""WebSocket live progress stream."""
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from api.routes import manager

router = APIRouter()


@router.websocket("/ws")
async def progress_socket(websocket: WebSocket):
    await websocket.accept()
    last = None
    try:
        while True:
            current = manager.latest
            if current != last:
                await websocket.send_json(current)
                last = current
            await asyncio.sleep(0.5)
    except (WebSocketDisconnect, RuntimeError):
        return
