"""Broadcasts live updates (game state, detected darts) to all connected WebSocket clients."""

import asyncio
import json
from typing import Any

import structlog

log = structlog.get_logger(__name__)

QUEUE_SIZE = 100


class EventHub:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        """Called at startup; publishing from worker threads is scheduled on this loop."""
        self._loop = loop

    def subscribe(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(QUEUE_SIZE)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        self._subscribers.discard(queue)

    def publish(self, message_type: str, payload: Any) -> None:
        """Thread-safe: may be called from request threads, camera threads or the loop."""
        if self._loop is None:
            return
        text = json.dumps({"type": message_type, "data": payload}, default=str)
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self._loop:
            self._deliver(text)
        else:
            self._loop.call_soon_threadsafe(self._deliver, text)

    def _deliver(self, text: str) -> None:
        for queue in list(self._subscribers):
            if queue.full():
                # a stalled client must not block the others; it will resync on reconnect
                queue.get_nowait()
            queue.put_nowait(text)
