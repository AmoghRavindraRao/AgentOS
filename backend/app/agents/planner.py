"""PlannerAgent: recall prior context → LLM decompose → list of subtasks.

Subtask queries must be independent and parallel-safe — the Researcher fan-out
runs them concurrently via asyncio.gather.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.agents.base import BaseAgent
from cognee import SearchType


@dataclass
class Subtask:
    id: str
    query: str


def _parse_subtasks(raw: str) -> list[Subtask]:
    """Extract subtask lines from LLM output.

    Accepts numbered lists (1. ...) or JSON arrays (["...", "..."]).
    Falls back to splitting on newlines.
    """
    # Try JSON array first
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [
                Subtask(id=str(i), query=str(q).strip())
                for i, q in enumerate(parsed)
                if str(q).strip()
            ]
    except (json.JSONDecodeError, ValueError):
        pass

    # Try numbered list: "1. some task"
    lines = re.findall(r"^\d+[.)]\s+(.+)", raw, re.MULTILINE)
    if lines:
        return [Subtask(id=str(i), query=q.strip()) for i, q in enumerate(lines)]

    # Fallback: non-empty lines
    lines = [ln.strip() for ln in raw.strip().splitlines() if ln.strip()]
    return [Subtask(id=str(i), query=q) for i, q in enumerate(lines[:5])]


def _hits_to_text(hits: list) -> str:
    if not hits:
        return "(no prior context)"
    return "\n\n".join(f"- {h.text[:400]}" for h in hits)


SYSTEM_PROMPT = """You are a research planning agent. 
Given a user query and any prior knowledge context, decompose the query into 
3 to 5 independent research subtasks.

Each subtask should be:
- A self-contained question or research directive
- Answerable independently (parallel-safe)
- Specific enough to guide a focused web search

Return ONLY a JSON array of subtask strings, e.g.:
["What are the main failure modes of multi-agent systems?", "How does memory affect agent coordination?"]

No explanations. No preamble. JSON array only."""


class PlannerAgent(BaseAgent):
    name = "planner"

    async def run(self, query: str, dataset_name: str) -> list[Subtask]:
        # 1. Recall prior domain context
        prior = await self.cognee.recall(
            dataset_name, query, k=8, query_type=SearchType.GRAPH_COMPLETION
        )
        await self._event("memory_read", dataset=dataset_name, query_type="GRAPH_COMPLETION")

        # 2. Ask LLM to decompose
        raw = await self.llm.complete(
            system=SYSTEM_PROMPT,
            user=f"Query: {query}\n\nPrior context from domain brain:\n{_hits_to_text(prior)}",
        )

        subtasks = _parse_subtasks(raw)

        # Ensure we always have at least 1 subtask even if LLM returns garbage
        if not subtasks:
            subtasks = [Subtask(id="0", query=query)]

        await self._event("planner_done", subtasks=[s.query for s in subtasks])
        return subtasks