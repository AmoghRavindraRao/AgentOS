"""ConfidenceReRanker: app-side recall re-ranking.

Critically, this NEVER mutates Cognee state. It reads recall() results and an
in-memory (Day 1) confidence map, computes an effective score from base
confidence + recency decay + upvote boost, drops anything forgotten or below the
floor, and returns a re-ordered list. On Day 3 the score store moves to the
`confidence` SQLite table.
"""

import dataclasses
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RecallHit:
    """Normalized recall result the re-ranker operates on."""

    source_data_id: str
    text: str
    raw_score: float = 0.5
    confidence: float = 0.0
    extra: dict = field(default_factory=dict)


@dataclass
class ConfidenceRow:
    score: float = 0.5
    upvotes: int = 0
    last_seen: float = field(default_factory=time.time)
    forgotten: bool = False


class ConfidenceReRanker:
    FLOOR = 0.15
    HALF_LIFE_DAYS = 30.0

    def __init__(self) -> None:
        # Day 1: in-memory store keyed by (dataset_name, source_data_id).
        # Day 3: back this with the `confidence` table.
        self._store: dict[tuple[str, str], ConfidenceRow] = {}

    def _get(self, dataset_name: str, data_id: str) -> Optional[ConfidenceRow]:
        return self._store.get((dataset_name, data_id))

    def _touch(self, dataset_name: str, data_id: str, last_seen: float) -> None:
        row = self._store.get((dataset_name, data_id))
        if row is None:
            row = ConfidenceRow(last_seen=last_seen)
            self._store[(dataset_name, data_id)] = row
        else:
            row.last_seen = last_seen

    def rank(self, dataset_name: str, hits: list[RecallHit]) -> list[RecallHit]:
        now = time.time()
        out: list[RecallHit] = []
        for h in hits:
            row = self._get(dataset_name, h.source_data_id)
            if row and row.forgotten:
                continue  # never surface forgotten nodes
            base = row.score if row else 0.5
            last_seen = row.last_seen if row else now
            recency = 0.5 ** (((now - last_seen) / 86400.0) / self.HALF_LIFE_DAYS)
            upvote_boost = min(0.3, 0.05 * (row.upvotes if row else 0))
            eff = max(0.0, min(1.0, (0.6 * h.raw_score + 0.4 * base) * recency + upvote_boost))
            if eff >= self.FLOOR:
                # dataclasses.replace — never mutate the input object.
                out.append(dataclasses.replace(h, confidence=eff))
            self._touch(dataset_name, h.source_data_id, last_seen=now)
        out.sort(key=lambda x: x.confidence, reverse=True)
        return out  # all confidence values in [0.0, 1.0]
