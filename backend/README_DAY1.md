# AgentOS Backend — Day 1 Foundation

Everything the Day 1 plan calls for, ready to run and smoke test.

## What's here

```
backend/
├── pyproject.toml            # dependency manifest (.toml for requirement install)
├── requirements.txt          # same deps for plain pip
├── .env.example              # copy to .env, add your LLM key
├── smoke_test.py             # exercises all 4 Cognee ops (remember/recall/improve/forget)
└── app/
    ├── main.py               # FastAPI app + lifespan (DB init), /health
    ├── config.py             # pydantic-settings
    ├── api/
    │   ├── deps.py           # demo auth, shared CogneeClient, DB session
    │   └── routes/domains.py # create/list + GET /domains/{id}/graph stub
    ├── db/
    │   ├── schema.sql        # canonical SQLite schema
    │   ├── models.py         # SQLModel: domains / sessions / sources / confidence
    │   └── session.py        # async engine + init_db()
    └── memory/
        ├── client.py         # CogneeClient — asyncio.Lock write serialization
        ├── domain_manager.py # _safe() slug -> dataset_name
        └── reranker.py       # ConfidenceReRanker (never writes to Cognee)
```

## Setup

```cmd
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e .
:: or: pip install -r requirements.txt

copy ..\.env .env
:: ensure LLM_API_KEY (or OPENAI_API_KEY) is set
```

> The repo root `.env` already has `LLM_API_KEY` / `OPENAI_API_KEY`. Copy it into
> `backend/.env` (or point pydantic-settings at it) before running.

## Smoke test Cognee (the Day 1 acceptance check)

```cmd
python smoke_test.py
```

Expected output (all green):

```
  PASS  remember() -> status=completed data_id=...
  PASS  recall() -> N result(s)
  PASS  improve() -> graph enrichment completed
  PASS  forget() -> dataset wiped

All four Cognee ops confirmed working. Day 1 memory layer is green.
```

## Run the API

```cmd
uvicorn app.main:app --reload --port 8000
```

- `GET  http://localhost:8000/health`
- `POST http://localhost:8000/api/v1/domains`  body: `{"slug":"ai-safety","title":"AI Safety"}`
- `GET  http://localhost:8000/api/v1/domains`
- `GET  http://localhost:8000/api/v1/domains/{id}/graph`  (empty graph until sources are ingested on Day 3)

## Cognee API corrections (validated against the vendored Cognee source)

The architecture docs had a few signatures that would fail at runtime. This code
uses the **correct** ones:

| Op | Docs said | Correct (used here) |
|----|-----------|---------------------|
| `improve` | `improve(dataset_name=..., session_ids=...)` | `improve(dataset=..., session_ids=...)` |
| `forget` source | `forget(data_id=...)` | `forget(data_id=..., dataset=...)` (data_id alone raises) |
| `remember` result | `result.items[0].id` | `result.items[0]["id"]` (items are dicts) |
| `recall` scope | (confirmed) | `recall(query_text=..., datasets=[ds], query_type=..., top_k=...)` |
| graph dump | (confirmed) | `await get_graph_engine()` then `await engine.get_graph_data()` |

`get_graph_data()` returns `(nodes, edges)` where `nodes` is a list of
`(node_id, props_dict)` and `edges` is a list of
`(source_id, target_id, relation, props_dict)`.

## Security note

`get_current_user` is a static demo-token check and currently allows
unauthenticated calls so the graph stub is easy to poke. Do not expose this
service publicly without real authentication.
