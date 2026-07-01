"""WriterAgent: recall → synthesize → grounding_check → improve().

The improve() call is the self-improvement step: it distills all researcher
findings from this session into the permanent domain knowledge graph.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from app.agents.base import BaseAgent
from app.agents.researcher import Finding
from cognee import SearchType


@dataclass
class Answer:
    text: str
    citations: list[str]
    grounded: bool
    ungrounded_claims: list[str]


def _hits_to_text(hits: list) -> str:
    if not hits:
        return "(no domain memory yet)"
    return "\n\n".join(f"[{i+1}] {h.text[:400]}" for i, h in enumerate(hits))


def _findings_to_text(findings: list[Finding]) -> str:
    if not findings:
        return "(no findings)"
    return "\n\n".join(
        f"[Finding from {f.source_uri}]\n{f.text[:400]}" for f in findings
    )


def _split_claims(text: str) -> list[str]:
    """Split report into individual sentences for grounding check."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    return [s.strip() for s in sentences if len(s.strip()) > 30]


def _has_support(claim: str, hits: list, findings: list[Finding]) -> bool:
    """Check if a claim has textual support in memory or findings."""
    claim_lower = claim.lower()
    # Extract key nouns (words > 5 chars as proxy)
    key_words = [w for w in re.findall(r"\b\w{5,}\b", claim_lower) if w not in STOP_WORDS]
    if not key_words:
        return True  # Skip very short/generic claims

    all_text = " ".join(
        [h.text.lower() for h in hits] + [f.text.lower() for f in findings]
    )
    # Grounded if at least 40% of key words appear in the evidence
    matches = sum(1 for w in key_words if w in all_text)
    return matches / len(key_words) >= 0.4


STOP_WORDS = {
    "about", "above", "after", "again", "against", "their", "there", "these",
    "which", "while", "where", "would", "could", "should", "other", "being",
    "using", "based", "entre", "through", "because", "before", "between",
}

SYNTHESIS_PROMPT = """You are a research synthesis agent.
Using the provided domain memory evidence and researcher findings, write a 
comprehensive, well-structured Markdown research report that directly answers 
the original query.

Requirements:
- Start with a clear executive summary (2-3 sentences)
- Use ## headers for major sections
- Cite sources inline using [1], [2], etc. referring to the numbered evidence
- End with a ## Key Takeaways section (3-5 bullet points)
- Be factual and grounded — only claim what the evidence supports
- Target 400-600 words"""


class WriterAgent(BaseAgent):
    name = "writer"

    async def run(
        self,
        query: str,
        findings: list[Finding],
        dataset_name: str,
        session_id: str,
    ) -> Answer:
        # 1. Recall full domain brain — use GRAPH_COMPLETION_DECOMPOSITION for
        #    multi-part evidence retrieval on complex synthesis queries
        context = await self.cognee.recall(
            dataset_name,
            query,
            k=12,
            query_type=SearchType.GRAPH_COMPLETION,
        )
        await self._event(
            "memory_read",
            dataset=dataset_name,
            query_type="GRAPH_COMPLETION",
        )

        # 2. Synthesize report
        draft = await self.llm.complete(
            system=SYNTHESIS_PROMPT,
            user=(
                f"Query: {query}\n\n"
                f"Domain memory evidence:\n{_hits_to_text(context)}\n\n"
                f"Researcher findings:\n{_findings_to_text(findings)}"
            ),
        )

        # 3. Grounding check — purely in-memory, zero extra Cognee calls
        claims = _split_claims(draft)
        ungrounded = [c for c in claims if not _has_support(c, context, findings)]
        grounded = len(ungrounded) == 0

        answer = Answer(
            text=draft,
            citations=[f.source_uri for f in findings if f.source_uri],
            grounded=grounded,
            ungrounded_claims=ungrounded,
        )

        await self._event(
            "writer_answer",
            grounded=grounded,
            ungrounded_count=len(ungrounded),
            preview=draft[:300],
        )

        # 4. IMPROVE — distill this session into permanent graph memory
        # Note: keyword arg is `dataset`, NOT `dataset_name` (corrected from README)
        try:
            await self.cognee.improve(dataset_name=dataset_name, session_ids=[session_id])
            await self._event("graph_updated", dataset=dataset_name)
        except Exception as e:
            # improve() failure must NOT block the answer delivery
            await self._event("improve_error", error=str(e))

        return answer