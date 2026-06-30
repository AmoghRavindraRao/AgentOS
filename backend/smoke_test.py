"""Day 1 Cognee smoke test — confirms all four memory ops work end to end.

Uses Cognee's embedded default stack (SQLite + LanceDB + Kuzu/Ladybug) — no
containers required. Run from the backend/ directory after installing deps:

    python smoke_test.py

It exercises, against a throwaway dataset:
    remember()  -> ingest + capture data_id (result.items[0]["id"])
    recall()    -> query scoped via datasets=[ds]  (NOT dataset_name=)
    improve()   -> session-free graph enrichment   (dataset=, keyword)
    forget()    -> wipe the dataset                 (dataset=)

Each op prints PASS/FAIL so a partial environment problem is obvious.
"""

import asyncio
import os
import sys

os.environ.setdefault("ENV", "dev")

import cognee

from app.memory.cognee_lifecycle import close_cognee_async_resources

DATASET = "agentos_smoke_test"


def _ok(msg: str) -> None:
    print(f"  PASS  {msg}")


def _fail(msg: str, err: Exception) -> None:
    print(f"  FAIL  {msg}: {type(err).__name__}: {err}")


async def main() -> int:
    if not (os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")):
        print(
            "WARNING: neither LLM_API_KEY nor OPENAI_API_KEY is set. "
            "remember()/improve() need an LLM for entity extraction and will fail.\n"
        )

    failures = 0

    # 1) REMEMBER -----------------------------------------------------------
    data_id = None
    try:
        result = await cognee.remember(
            "AgentOS is a multi-agent research platform. Cognee provides its "
            "persistent, domain-scoped knowledge brain.",
            dataset_name=DATASET,
            run_in_background=False,
            self_improvement=False,
        )
        await result
        # items are dicts: data_id = result.items[0]["id"]
        if getattr(result, "items", None):
            first = result.items[0]
            data_id = first.get("id") if isinstance(first, dict) else getattr(first, "id", None)
        data_id = data_id or getattr(result, "dataset_id", None)
        _ok(f"remember() -> status={result.status} data_id={data_id}")
    except Exception as e:  # noqa: BLE001
        _fail("remember()", e)
        failures += 1

    # 2) RECALL -------------------------------------------------------------
    try:
        hits = await cognee.recall(
            query_text="What is AgentOS?",
            datasets=[DATASET],
            query_type=cognee.SearchType.GRAPH_COMPLETION,
            top_k=3,
        )
        _ok(f"recall() -> {len(hits)} result(s)")
        if hits:
            preview = str(getattr(hits[0], "content", hits[0]))[:120]
            print(f"        first hit: {preview!r}")
    except Exception as e:  # noqa: BLE001
        _fail("recall()", e)
        failures += 1

    # 3) IMPROVE ------------------------------------------------------------
    try:
        # No session_ids on Day 1: this runs the default graph enrichment stage.
        # keyword arg is `dataset`, not `dataset_name`.
        await cognee.improve(dataset=DATASET)
        _ok("improve() -> graph enrichment completed")
    except Exception as e:  # noqa: BLE001
        _fail("improve()", e)
        failures += 1

    # 4) FORGET -------------------------------------------------------------
    try:
        await cognee.forget(dataset=DATASET)
        _ok("forget() -> dataset wiped")
    except Exception as e:  # noqa: BLE001
        _fail("forget()", e)
        failures += 1

    print()
    if failures == 0:
        print("All four Cognee ops confirmed working. Day 1 memory layer is green.")
        return 0
    print(f"{failures} op(s) failed — see messages above.")
    return 1


if __name__ == "__main__":
    async def _main_with_cleanup() -> int:
        try:
            return await main()
        finally:
            await close_cognee_async_resources()

    sys.exit(asyncio.run(_main_with_cleanup()))
