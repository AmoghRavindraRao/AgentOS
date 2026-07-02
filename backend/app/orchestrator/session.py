"""SessionOrchestrator: Plan → Fan-out → Fan-in → Write → Improve."""
from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

from app.agents.llm import LLMClient
from app.agents.planner import PlannerAgent
from app.agents.researcher import ResearcherAgent
from app.agents.writer import WriterAgent, Answer
from app.db.models import Domain, Session as SessionModel
from app.db.session import async_session_factory
from app.memory.client import CogneeClient
from app.orchestrator.events import event_bus


class SessionOrchestrator:
    def __init__(self, cognee: CogneeClient, llm_model: str = "gpt-4o-mini") -> None:
        self._cognee = cognee
        self._llm_model = llm_model

    def _make_llm(self) -> LLMClient:
        return LLMClient(model=self._llm_model)

    async def run_session(self, domain: Domain, query: str, session_id: str) -> Answer:
        ds = domain.dataset_name

        event_bus.create(session_id)

        async def emit(event: dict[str, Any]) -> None:
            await event_bus.emit(session_id, event)

        async with async_session_factory() as db:
            session_row = SessionModel(
                id=session_id,
                domain_id=domain.id,
                query=query,
                status="planning",
            )
            db.add(session_row)
            await db.commit()

        await emit({
            "type": "session_start",
            "session_id": session_id,
            "domain": ds,
            "query": query,
            "ts": time.time(),
        })

        try:
            # 1. PLAN
            await self._set_status(session_id, "planning")
            llm = self._make_llm()
            planner = PlannerAgent(cognee=self._cognee, llm=llm, emit=emit, session_id=session_id)
            subtasks = await planner.run(query, ds)

            # 2. FAN-OUT
            await self._set_status(session_id, "researching")

            def make_researcher() -> ResearcherAgent:
                return ResearcherAgent(cognee=self._cognee, llm=self._make_llm(), emit=emit, session_id=session_id)

            results = await asyncio.gather(
                *[make_researcher().run(st, ds) for st in subtasks],
                return_exceptions=True,
            )

            findings = [f for r in results if not isinstance(r, Exception) for f in r]

            for r in results:
                if isinstance(r, Exception):
                    await emit({"type": "researcher_error", "session_id": session_id, "error": str(r), "ts": time.time()})

            # 3. WRITE
            await self._set_status(session_id, "writing")
            writer = WriterAgent(cognee=self._cognee, llm=llm, emit=emit, session_id=session_id)
            answer = await writer.run(query, findings, ds, session_id)

            # 4. PERSIST
            await self._set_status(session_id, "complete", output=answer.text)
            await emit({"type": "session_complete", "session_id": session_id, "grounded": answer.grounded, "ts": time.time()})
            return answer

        except Exception as e:
            await self._set_status(session_id, "error")
            await emit({"type": "session_error", "session_id": session_id, "error": str(e), "ts": time.time()})
            raise

    async def _set_status(self, session_id: str, status: str, output: str | None = None) -> None:
        async with async_session_factory() as db:
            row = await db.get(SessionModel, session_id)
            if row:
                row.status = status
                if output:
                    row.output = output
                if status == "complete":
                    row.completed_at = time.time()
                await db.commit()