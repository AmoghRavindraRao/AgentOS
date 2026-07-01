"""BaseAgent: shared foundation for Planner, Researcher, and Writer.

Every agent gets:
  - self.cognee  : the shared CogneeClient (write lock lives there)
  - self.llm     : thin async OpenAI wrapper
  - self._event(): emits a typed SSE event into the EventBus for this session
"""
from __future__ import annotations

import json
import time
from typing import Any, Callable, Coroutine

from app.memory.client import CogneeClient
from app.agents.llm import LLMClient


class BaseAgent:
    name: str = "base"

    def __init__(
        self,
        cognee: CogneeClient,
        llm: LLMClient,
        emit: Callable[..., Coroutine[Any, Any, None]],
        session_id: str,
    ) -> None:
        self.cognee = cognee
        self.llm = llm
        self._emit = emit
        self._session_id = session_id

    async def _event(self, event_type: str, **kwargs: Any) -> None:
        """Push a typed SSE event. Always includes agent name, session_id, ts."""
        payload = {
            "type": event_type,
            "agent": self.name,
            "session_id": self._session_id,
            "ts": time.time(),
            **kwargs,
        }
        await self._emit(payload)