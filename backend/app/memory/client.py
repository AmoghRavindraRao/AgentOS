"""CogneeClient: the single choke-point for every Cognee call.

Responsibilities:
  * Namespace every operation by ``dataset_name`` (domain isolation / hot-swap).
  * Serialize ``remember()`` writes with an ``asyncio.Lock`` — the embedded
    graph store does not support concurrent writes from parallel coroutines
    (parallel researcher fan-out on Day 2).
  * Centralize the *correct* Cognee API signatures so the rest of the codebase
    never has to remember them.

API signatures below were validated directly against the Cognee source in this
workspace. Where the project README disagreed, this file is correct:

  remember(data, dataset_name=...)            -> RememberResult
      data_id  = result.items[0]["id"]        (items are dicts, not objects)
  recall(query_text=..., datasets=[ds], ...)  -> list[RecallResponse]
      scope is `datasets=` (a list), NOT `dataset_name=`
  improve(dataset=..., session_ids=[...])     keyword arg is `dataset`, not `dataset_name`
  forget(data_id=..., dataset=...)            data_id REQUIRES a dataset
  forget(dataset=...)                         wipes a whole domain
"""

import asyncio
import os
from typing import Any, Optional

# Keep local AgentOS runs from spawning Cognee telemetry sessions unless an
# environment explicitly opts into a different mode.
os.environ.setdefault("ENV", "dev")

import cognee  # noqa: E402
from cognee import SearchType  # noqa: E402
from cognee.infrastructure.databases.graph import get_graph_engine  # noqa: E402

from app.memory.reranker import ConfidenceReRanker, RecallHit


def _extract_data_id(result: Any) -> Optional[str]:
    """Pull the stable data_id out of a RememberResult.

    ``result.items`` is a list of dicts (e.g. ``{"id": "...", "name": ...}``).
    Fall back to ``dataset_id`` when no per-item id is available (e.g. the
    background path hasn't resolved items yet).
    """
    items = getattr(result, "items", None)
    if items:
        first = items[0]
        if isinstance(first, dict):
            data_id = first.get("id")
            if data_id:
                return str(data_id)
        # Defensive: some builds may hand back objects.
        data_id = getattr(first, "id", None)
        if data_id:
            return str(data_id)
    dataset_id = getattr(result, "dataset_id", None)
    return str(dataset_id) if dataset_id else None


def _hit_text(r: Any) -> str:
    """Best-effort text extraction from a RecallResponse entry."""
    for attr in ("content", "text", "answer"):
        val = getattr(r, attr, None)
        if val:
            return str(val)
    return str(r)


def _hit_id(r: Any) -> str:
    """Best-effort stable id for a recall entry (for confidence keying)."""
    for attr in ("id", "node_id", "source", "source_data_id"):
        val = getattr(r, attr, None)
        if val:
            return str(val)
    return _hit_text(r)[:64]


def _hit_score(r: Any) -> float:
    for attr in ("score", "reranked_score", "relevance"):
        val = getattr(r, attr, None)
        if isinstance(val, (int, float)):
            return float(val)
    return 0.5


def _to_hit(r: Any) -> RecallHit:
    return RecallHit(
        source_data_id=_hit_id(r),
        text=_hit_text(r),
        raw_score=_hit_score(r),
    )


class CogneeClient:
    def __init__(self, reranker: Optional[ConfidenceReRanker] = None) -> None:
        self._rerank = reranker or ConfidenceReRanker()
        self._write_lock = asyncio.Lock()  # guards all remember() writes

    # -- writes ------------------------------------------------------------

    async def ingest(self, dataset_name: str, text: str) -> Optional[str]:
        """Ingest a whole source document into the domain's permanent graph.

        Blocks until indexed so a subsequent recall() sees it immediately.
        Returns the cognee_data_id (handle for forget(data_id=...)).
        """
        async with self._write_lock:
            result = await cognee.remember(
                text,
                dataset_name=dataset_name,
                run_in_background=False,
                self_improvement=False,  # improve() runs explicitly at session end
            )
            await result  # no-op when blocking; awaits the task in bg mode
        return _extract_data_id(result)

    async def remember(self, dataset_name: str, text: str) -> Optional[str]:
        """Persist a researcher finding into the domain brain."""
        async with self._write_lock:
            result = await cognee.remember(text, dataset_name=dataset_name)
            await result
        return _extract_data_id(result)

    # -- reads -------------------------------------------------------------

    async def recall(
        self,
        dataset_name: str,
        query: str,
        k: int = 10,
        query_type: SearchType = SearchType.GRAPH_COMPLETION,
    ) -> list[RecallHit]:
        """Query the domain brain, then apply the app-side confidence re-rank.

        Note the scope param is ``datasets=[dataset_name]`` (a list) — NOT
        ``dataset_name=``, which recall() silently ignores.
        """
        raw = await cognee.recall(
            query_text=query,
            datasets=[dataset_name],
            query_type=query_type,
            top_k=k * 3,  # over-fetch; the re-ranker trims to k
        )
        hits = [_to_hit(r) for r in raw]
        ranked = self._rerank.rank(dataset_name, hits)
        return ranked[:k]

    # -- self-improvement --------------------------------------------------

    async def improve(self, dataset_name: str, session_ids: list[str]) -> None:
        """Distill session findings into permanent graph memory."""
        await cognee.improve(dataset=dataset_name, session_ids=session_ids)

    # -- forgetting --------------------------------------------------------

    async def forget_source(self, dataset_name: str, data_id: str) -> None:
        """Remove one source document and its derived nodes.

        forget(data_id=...) requires a dataset reference — passing data_id
        alone raises ValueError in Cognee.
        """
        await cognee.forget(data_id=data_id, dataset=dataset_name)

    async def forget_domain(self, dataset_name: str) -> None:
        """Wipe an entire domain brain."""
        await cognee.forget(dataset=dataset_name)

    # -- brain visualization ----------------------------------------------

    async def get_graph_snapshot(self, dataset_name: str) -> dict:
        """Raw node/edge dump for react-force-graph-2d.

        Uses get_graph_engine().get_graph_data() — NOT recall(NATURAL_LANGUAGE),
        which returns LLM text rather than a node/edge list.

        get_graph_data() returns:
          nodes: list[(node_id, props_dict)]
          edges: list[(source_id, target_id, relation, props_dict)]
        """
        graph_engine = await get_graph_engine()
        nodes, edges = await graph_engine.get_graph_data()
        return _format_for_graph(nodes, edges)


def _format_for_graph(nodes: list, edges: list) -> dict:
    """Reshape Cognee's (nodes, edges) tuples into the BrainGraph JSON shape."""
    out_nodes = []
    for n in nodes:
        node_id, props = (n[0], n[1]) if isinstance(n, (tuple, list)) else (None, {})
        props = props or {}
        out_nodes.append(
            {
                "id": str(node_id),
                "label": props.get("name") or props.get("label") or str(node_id),
                "group": props.get("type", "Entity"),
            }
        )

    out_links = []
    for e in edges:
        if isinstance(e, (tuple, list)) and len(e) >= 3:
            out_links.append(
                {"source": str(e[0]), "target": str(e[1]), "relation": str(e[2])}
            )
    return {"nodes": out_nodes, "links": out_links}
