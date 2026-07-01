"""SSE stream endpoint.

GET /api/v1/sessions/{session_id}/stream

Streams AgentEvent JSON objects as server-sent events. The client connects
once and receives all events until session_complete or session_error arrives.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.orchestrator.events import event_bus

router = APIRouter(prefix="/api/v1", tags=["stream"])

TERMINAL_EVENTS = {"session_complete", "session_error"}


@router.get("/sessions/{session_id}/stream")
async def stream_session(session_id: str):
    """Live SSE feed for a running session."""
    q = event_bus.subscribe(session_id)

    async def generator():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    # Send a heartbeat to keep the connection alive
                    yield {"data": json.dumps({"type": "heartbeat"})}
                    continue

                yield {"data": json.dumps(event)}

                if event.get("type") in TERMINAL_EVENTS:
                    break
        finally:
            event_bus.cleanup(session_id)

    return EventSourceResponse(generator())