"""
Full end-to-end pipeline verification.
Runs a session and streams all SSE events to stdout.
"""
import asyncio
import json
import httpx

BASE = "http://localhost:8000/api/v1"
HEADERS = {}

DOMAIN_ID = "60b3b54e52054aa68ecff3e823517913"
QUERY = "How do techniques like RLHF, Constitutional AI, and Chain-of-Thought prompting address the core challenges of AI alignment and reward specification?"

async def run_and_stream():
    async with httpx.AsyncClient(base_url=BASE, headers=HEADERS, timeout=30) as client:

        # 1. Fire the run
        print(f"🚀 Starting session...\n   Query: {QUERY[:80]}...")
        r = await client.post(f"/domains/{DOMAIN_ID}/run", json={"query": QUERY})
        r.raise_for_status()
        data = r.json()
        session_id = data["session_id"]
        print(f"   session_id = {session_id}\n")

    # 2. Stream SSE events (separate client with no timeout)
    print("📡 Streaming events:\n" + "-"*50)
    events_seen = []
    async with httpx.AsyncClient(base_url=BASE, headers=HEADERS, timeout=None) as client:
        async with client.stream("GET", f"/sessions/{session_id}/stream") as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data:"):
                    raw = line[5:].strip()
                    if not raw:
                        continue
                    try:
                        evt = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    etype = evt.get("type", "?")
                    events_seen.append(etype)

                    if etype == "session_start":
                        print(f"  🟢 session_start — domain: {evt.get('domain')}")
                    elif etype == "planner_done":
                        subtasks = evt.get("subtasks", [])
                        print(f"  📋 planner_done — {len(subtasks)} subtasks:")
                        for s in subtasks:
                            print(f"       • {s[:80]}")
                    elif etype == "memory_read":
                        print(f"  🧠 memory_read — agent: {evt.get('agent','?')}")
                    elif etype == "memory_write":
                        print(f"  💾 memory_write — preview: {evt.get('preview','')[:60]}")
                    elif etype == "researcher_finding":
                        print(f"  🔍 researcher_finding — {evt.get('text','')[:80]}...")
                    elif etype == "writer_answer":
                        grounded = evt.get("grounded", False)
                        flag = "✅" if grounded else "⚠️"
                        print(f"  ✍️  writer_answer — grounded: {flag} | ungrounded: {evt.get('ungrounded_count', 0)}")
                    elif etype == "graph_updated":
                        print(f"  🕸️  graph_updated — improve() fired")
                    elif etype == "session_complete":
                        print(f"  🏁 session_complete\n" + "-"*50)
                        break
                    elif etype == "session_error":
                        print(f"  ❌ session_error: {evt.get('error')}")
                        break
                    elif etype == "heartbeat":
                        print(f"  💓 heartbeat (pipeline still running...)")
                    elif etype == "researcher_error":
                        print(f"  ⚠️  researcher_error: {evt.get('error','')[:100]}")

    # 3. Poll final output
    print("\n📄 Final output:")
    async with httpx.AsyncClient(base_url=BASE, headers=HEADERS, timeout=15) as client:
        r = await client.get(f"/sessions/{session_id}")
        r.raise_for_status()
        session = r.json()
        print(f"   Status: {session['status']}")
        if session.get("output"):
            print(f"\n{'='*50}")
            print(session["output"][:1500])
            print(f"{'='*50}")

    # 4. Summary check
    print(f"\n✅ Events observed: {events_seen}")
    required = {"session_start", "planner_done", "memory_read", "memory_write", "writer_answer", "graph_updated", "session_complete"}
    missing = required - set(events_seen)
    if missing:
        print(f"⚠️  Missing expected events: {missing}")
    else:
        print("🎉 All 4 Cognee ops fired (remember, recall, improve, and forget available via DELETE /sources)")

if __name__ == "__main__":
    asyncio.run(run_and_stream())