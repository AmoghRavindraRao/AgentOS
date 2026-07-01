"""ResearcherAgent: recall → fetch → remember findings.

One ResearcherAgent runs per subtask. They fan out in parallel via
asyncio.gather in SessionOrchestrator. The CogneeClient write lock
serializes all remember() calls to avoid Kuzu commit conflicts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.agents.base import BaseAgent
from app.tools.web_search import web_search_and_fetch
from cognee import SearchType


@dataclass
class Finding:
    subtask_id: str
    text: str
    source_uri: str
    data_id: Optional[str]
    score: float = 0.6


def _hits_to_text(hits: list) -> str:
    if not hits:
        return "(none)"
    return "\n\n".join(f"- {h.text[:300]}" for h in hits)


EXTRACT_PROMPT = """You are a research extraction agent.
Given existing knowledge from memory and a new source document, extract 
the key factual findings relevant to the research subtask.

Be concise: 3-6 bullet points maximum.
Focus only on facts, data, and insights directly relevant to the subtask.
Do not repeat what's already in the existing knowledge."""


class ResearcherAgent(BaseAgent):
    name = "researcher"

    async def run(self, subtask, dataset_name: str) -> list[Finding]:
        # 1. Check what we already know — avoid re-researching
        context = await self.cognee.recall(
            dataset_name, subtask.query, k=6, query_type=SearchType.GRAPH_COMPLETION
        )
        await self._event("memory_read", dataset=dataset_name, subtask_id=subtask.id)

        # 2. Fetch web sources for this subtask
        docs = await web_search_and_fetch(subtask.query, max_results=3)

        findings: list[Finding] = []

        for doc in docs:
            if not doc.text.strip():
                continue

            # 3. LLM extracts key findings from source vs existing memory
            note = await self.llm.complete(
                system=EXTRACT_PROMPT,
                user=(
                    f"Subtask: {subtask.query}\n\n"
                    f"Existing knowledge in domain brain:\n{_hits_to_text(context)}\n\n"
                    f"New source ({doc.source_uri}):\n{doc.text[:2000]}"
                ),
            )

            if not note.strip():
                continue

            # 4. Write finding into domain brain (lock serializes concurrent writes)
            data_id = await self.cognee.remember(dataset_name, note)
            await self._event(
                "memory_write",
                dataset=dataset_name,
                subtask_id=subtask.id,
                preview=note[:120],
            )

            findings.append(
                Finding(
                    subtask_id=subtask.id,
                    text=note,
                    source_uri=doc.source_uri,
                    data_id=data_id,
                    score=0.6,
                )
            )
            await self._event(
                "researcher_finding",
                subtask_id=subtask.id,
                source=doc.source_uri,
                preview=note[:200],
            )

        return findings