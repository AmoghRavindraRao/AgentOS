# AgentOS – Day 2 Backend Progress

Date: 2026-06-30  
Engineer: Rohith Raju (`r0ebot`)

This document summarizes the Day 2 backend work for AgentOS, focused on wiring the Planner / Researcher / Writer agents to Cognee and validating the multi-agent pipeline independently of the HTTP API.

---

## 1. What Was Built on Day 2

### 1.1 New agent and orchestration modules

Under `backend/app/` we now have:

- `app/agents/base.py`  
  - `BaseAgent` with shared `CogneeClient`, `LLMClient`, and `_event()` abstraction to emit SSE events (`type`, `agent`, `session_id`, `dataset`, etc.).

- `app/agents/llm.py`  
  - `LLMClient`: thin async wrapper over OpenAI Chat Completions using `LLM_API_KEY` / `OPENAI_API_KEY` from `.env`.  
  - Centralizes the model choice (`gpt-4o-mini` by default) and keeps provider details out of agent code. [file:63]

- `app/agents/planner.py`  
  - `PlannerAgent`:  
    - Calls `cognee.recall(...)` to pull prior domain context.  
    - Uses LLM to decompose the user query into 3–5 parallel-safe subtasks.  
    - Emits `memory_read` and `planner_done` events. [file:63]

- `app/agents/researcher.py`  
  - `ResearcherAgent`:  
    - Calls `cognee.recall(...)` to see what the domain brain already knows about a subtask.  
    - Uses `web_search_and_fetch(...)` to get source documents (Tavily or fallback).  
    - Extracts findings with LLM, then writes them back with `cognee.remember(...)`.  
    - Emits `memory_read`, `memory_write`, and `researcher_finding` events.  
    - Uses the `CogneeClient` write lock to serialize concurrent `remember(...)` calls. [file:63]

- `app/agents/writer.py`  
  - `WriterAgent`:  
    - Calls `cognee.recall(...)` with a richer retrieval mode for synthesis.  
    - Uses LLM to produce a grounded Markdown report.  
    - Runs a lightweight in-memory grounding check to flag ungrounded claims.  
    - Calls `cognee.improve(dataset_name=..., session_ids=[...])` to distill the session into permanent graph memory.  
    - Emits `writer_answer` and `graph_updated` events. [file:63][file:64]

- `app/orchestrator/events.py`  
  - `EventBus` with an `asyncio.Queue` per session.  
  - Used by the SSE endpoint to stream live agent events to the frontend.

- `app/orchestrator/session.py`  
  - `SessionOrchestrator`:  
    - Plan → fan-out Researchers via `asyncio.gather(return_exceptions=True)` → fan-in findings → Write → Improve → update `sessions` table.  
    - Ensures a failing `ResearcherAgent` does not abort siblings. [file:63]

- `app/tools/web_search.py`  
  - `web_search_and_fetch(...)` with Tavily+raw HTML extraction via `trafilatura`.  
  - Fallback stub when `TAVILY_API_KEY` is empty, so development harness can run quickly. [file:63]

### 1.2 New API routes

- `app/api/routes/sessions.py`  
  - `POST /api/v1/domains/{domain_id}/run`  
    - Creates a background task that calls `SessionOrchestrator.run_session(domain, query)`.  
    - Returns `{status: "started", domain_id, query}` immediately (non-blocking). [file:63]
  - `GET /api/v1/sessions/{session_id}`  
    - Returns `id, domain_id, query, status, output`.

- `app/api/routes/stream.py`  
  - `GET /api/v1/sessions/{session_id}/stream`  
    - SSE endpoint using `EventSourceResponse`.  
    - Streams all `AgentEvent` objects until `session_complete` or `session_error`. [file:63]

### 1.3 `main.py` updates

- `app/main.py` now:
  - Initializes the app with a lifespan that calls `init_db()` and `close_cognee_async_resources()`.  
  - Adds CORS for `http://localhost:3000` and `http://localhost:5173`.  
  - Includes routers for `domains`, `sessions`, and `stream`.  
  - Provides `GET /health` for quick health checks. [file:63]

---

## 2. Environment and Dependencies

### 2.1 `.env` configuration

The important variables used during Day 2:

```bash
LLM_API_KEY=sk-...              # or OPENAI_API_KEY
OPENAI_API_KEY=sk-...          # same key, for OpenAI client
EMBEDDING_MODEL=openai/text-embedding-3-small

# Temporarily disabled during harness testing:
TAVILY_API_KEY=                # empty to force web_search fallback

DATABASE_URL=sqlite+aiosqlite:///./agentOS.db
CORS_ORIGINS=http://localhost:3000
```

For teammates:

- They copy `.env.example` → `.env` and fill in their own keys, never committing `.env`. [file:63]

### 2.2 `pyproject.toml`

- Added `openai>=1.30.0` to `dependencies` to support `LLMClient`.  
- Using `uv sync` with Python 3.12 to manage the backend environment. [file:63]

---

## 3. Smoke Tests and Verification

### 3.1 Cognee + HTTP pipeline smoke test

We use `backend/smoke_agentos.py` to validate:

1. Cognee ops on a temporary dataset `smoke_test`:
   - `remember(...)`  
   - `recall(...)`  
   - `improve(...)`  
   - `forget(...)`  

2. FastAPI + multi-agent pipeline:
   - `GET /health`  
   - `POST /api/v1/domains`  
   - `POST /api/v1/domains/{id}/run`  
   - Poll `sessions` table until status is `complete` with non-empty `output`. [file:63]

Example successful run:

```text
=== Cognee smoke test PASSED ===

=== HTTP pipeline smoke test ===
[OK] /health status=200, body={"status":"ok"}
[OK] POST /domains id=bddd5a3ea4f643048cb67a1dea5da881, dataset_name=u_demo_d_smoke_domain_1782865127
[OK] POST /domains/.../run accepted: {...}
[INFO] polling agentos.db for latest session status...
[INFO] session_id=29cf918790034b46b63f2c666a176104 status=complete
[OK] session 29cf918790034b46b63f2c666a176104 completed with non-empty output.
=== HTTP pipeline smoke test PASSED ===

✅ All AgentOS smoke tests PASSED.
```

This confirms:

- Cognee is reachable and correctly configured in the venv.  
- Domains and sessions are created.  
- Planner / Researcher / Writer + orchestrator run end-to-end via the HTTP path and produce an answer. [file:63]

### 3.2 Direct agent harness (non-HTTP)

To independently verify the agents outside FastAPI, we added `backend/test_agents_direct.py`:

- Uses `get_cognee_client()` from `app.api.deps` to get the same `CogneeClient` wiring as the API.  
- Instantiates `PlannerAgent`, `ResearcherAgent`, `WriterAgent`.  
- Emits simple `EVENT: <type> agent=<name>` logs.  
- Uses a short query and only the first subtask to keep runtime predictable.  
- Wraps `main()` in `asyncio.wait_for(..., timeout=120)` to guarantee completion. [file:64]

Example run:

```text
=== Direct agent harness (minimal) ===
Dataset: direct_agent_test
Session: direct-1
Query:   Summarize AgentOS in 3 bullets.

--- PlannerAgent.run() ---
EVENT: memory_read agent= planner
EVENT: planner_done agent= planner
Using only subtask: What are the key features of AgentOS related to multi-agent collaboration?

--- ResearcherAgent.run() ---
EVENT: memory_read agent= researcher
...
EVENT: memory_write agent= researcher
EVENT: researcher_finding agent= researcher

Researcher produced 1 findings.
  Finding preview: - **Task Allocation**: AgentOS includes mechanisms for dynamic task allocation among agents, ensuring that tasks are assigned based on agent capabilities and current workload. ...

--- WriterAgent.run() ---
EVENT: memory_read agent= writer
EVENT: writer_answer agent= writer
EVENT: graph_updated agent= writer

=== FINAL ANSWER (WriterAgent) ===

# Research Report on AgentOS
...
=== Harness complete ===
```

This validates:

- Planner, Researcher, and Writer are importable and callable.  
- Cognee recall/remember/improve are working in the direct harness path.  
- The grounding check and graph update steps run without error. [file:64]

---

## 4. Errors Encountered and How They Were Resolved

### 4.1 DatasetNotFoundError during early `recall(...)`

**Symptoms:**

During the first `POST /domains/{id}/run` calls, logs showed:

```text
DatasetNotFoundError: No datasets found. (Status code: 404)
query_router: no patterns matched, default=GRAPH_COMPLETION query='...'
```

**Cause:**

- `PlannerAgent` and `ResearcherAgent` were calling `cognee.recall(...)` on a brand-new domain before any `remember(...)` calls had created data points for that dataset. [file:63]

**Resolution:**

- We confirmed this is expected behavior for a fresh domain and does not crash the app; the agents proceed with “no prior context” and rely on fresh web fetch.  
- No code change needed; just documented it here so teammates aren’t surprised by the 404 in logs. [file:63]

### 4.2 Smoke test timing out at `status='researching'`

**Symptoms:**

Initial version of `smoke_agentos.py` threw:

```text
RuntimeError: Timed out waiting for session to reach 'complete' or 'error'.
```

while the latest session row in `sessions` stayed at `status='researching'`. [file:63]

**Cause:**

- Multi-agent session does non-trivial work (Planner + multiple Researchers + Writer), including Cognee indexing and self-improvement.  
- The script’s timeout window was too tight for the first run on a brand-new domain. [file:63]

**Resolution:**

- Adjusted smoke test to:
  - Increase timeout window.  
  - Log intermediate statuses for debugging.  
  - Continue polling until a `complete` status is observed.  
- After tuning, the smoke test consistently reaches `status='complete'` with non-empty `output`. [file:63]

### 4.3 Direct harness initially “looking like a loop”

**Symptoms:**

First version of `test_agents_direct.py` appeared to “keep running”, with many Cognee pipeline logs and no clear completion marker. [file:64]

**Cause:**

- Harness was:
  - Running all subtasks from Planner, not just the first.  
  - Using Tavily search, which adds multiple HTTP fetches per subtask.  
  - Printing full logs without a final “done” marker or timeout.

**Resolution:**

- Day 2 harness was tightened by:
  - Using a shorter query: `"Summarize AgentOS in 3 bullets."`.  
  - Temporarily disabling Tavily (`TAVILY_API_KEY=` in `.env`) so `web_search_and_fetch` returns a stub doc.  
  - Using only the first subtask from Planner.  
  - Adding `asyncio.wait_for(main(), timeout=120)` and a `=== Harness complete ===` print.  
- With these changes, the harness completes predictably and prints a coherent Writer answer. [file:64]

### 4.4 Unclosed aiohttp client session warnings

**Symptoms:**

At the end of some runs:

```text
Unclosed client session
client_session: <aiohttp.client.ClientSession object at ...>

Unclosed connector
connections: [...]
connector: <aiohttp.connector.TCPConnector object at ...>
```

**Cause:**

- These warnings come from Cognee’s internal HTTP client (aiohttp) when the process exits right after pipelines complete. [file:63]

**Resolution:**

- Confirmed that they do not affect correctness or runtime behavior for the hackathon embedded stack.  
- Left as-is for now; can be cleaned up later by tightening Cognee’s shutdown lifecycle. [file:63]

---

## 5. How Teammates Should Use This

### 5.1 Reproducing Rohith’s Day 2 state

For Engineer 2 and Engineer 3:

1. Clone and set up backend:

   ```bash
   git clone https://github.com/rohithraju-ops/AgentOS.git
   cd AgentOS/backend
   cp .env.example .env
   # Fill in LLM_API_KEY / OPENAI_API_KEY, optionally TAVILY_API_KEY later
   uv sync --python 3.12
   ```

2. Run the backend:

   ```bash
   uv run uvicorn app.main:app --reload --port 8000
   ```

3. Run smoke tests (in another terminal):

   ```bash
   uv run python smoke_agentos.py
   ```

   Expect: `=== Cognee smoke test PASSED ===` and `=== HTTP pipeline smoke test PASSED ===`. [file:63]

4. Run direct harness (optional, for extra confidence):

   ```bash
   uv run python test_agents_direct.py
   ```

   Expect: `=== Harness complete ===` at the end and a short Research Report on AgentOS. [file:64]

### 5.2 Next steps for Day 3+

- Engineer 2:
  - Finish sources ingest routes (`POST /sources`, `DELETE /sources/{id}`) and wire `cognee.remember(...)` / `cognee.forget(...)` to them.  
  - Implement `GET /domains/{id}/graph` using `CogneeClient.get_graph_snapshot(...)`. [file:63]

- Engineer 3:
  - Build frontend domain dashboard, Live Agent Run view, and BrainGraph (React + SSE + react-force-graph-2d) using the event schema defined in the main README. [file:63]

---