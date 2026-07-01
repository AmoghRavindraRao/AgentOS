"""EventBus: one asyncio.Queue per active session.

The SSE stream endpoint subscribes by session_id. Agents emit via
SessionOrchestrator._emit() which puts events onto the right queue.
"""
from __future__ import annotations

import asyncio
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[Any]] = {}

    def create(self, session_id: str) -> asyncio.Queue[Any]:
        """Register a new queue for a session. Call before starting the session."""
        q: asyncio.Queue[Any] = asyncio.Queue()
        self._queues[session_id] = q
        return q

    def subscribe(self, session_id: str) -> asyncio.Queue[Any]:
        """Get the queue for an existing session (SSE endpoint uses this)."""
        if session_id not in self._queues:
            # Late subscribe: create so SSE doesn't crash
            return self.create(session_id)
        return self._queues[session_id]

    async def emit(self, session_id: str, event: dict[str, Any]) -> None:
        """Put an event onto a session's queue (non-blocking)."""
        q = self._queues.get(session_id)
        if q is not None:
            await q.put(event)

    def cleanup(self, session_id: str) -> None:
        """Remove the queue after SSE stream closes."""
        self._queues.pop(session_id, None)


# Process-wide singleton — imported by routes and orchestrator
event_bus = EventBus()