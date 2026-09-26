"""WebSocket for live updates: every client gets the current game on connect and then all
changes (from any device or from the cameras)."""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from dartscore.services.games import GameService
from dartscore.services.hub import EventHub

router = APIRouter()


@router.websocket("/ws")
async def live(websocket: WebSocket) -> None:
    await websocket.accept()
    hub: EventHub = websocket.app.state.hub
    games: GameService = websocket.app.state.games
    queue = hub.subscribe()
    try:
        await websocket.send_text(
            json.dumps({"type": "game", "data": games.active_state()}, default=str)
        )

        async def forward() -> None:
            while True:
                await websocket.send_text(await queue.get())

        async def drain() -> None:
            # clients only send keep-alive pings; closing ends the connection
            while True:
                await websocket.receive_text()

        done, pending = await asyncio.wait(
            [asyncio.create_task(forward()), asyncio.create_task(drain())],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        for task in done:
            if (exc := task.exception()) and not isinstance(exc, WebSocketDisconnect):
                raise exc
    except WebSocketDisconnect:
        pass
    finally:
        hub.unsubscribe(queue)
