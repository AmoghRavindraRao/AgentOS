# backend/test_agents_direct.py

import asyncio
from typing import Any, Dict

from app.api.deps import get_cognee_client  # same wiring as FastAPI
from app.agents.llm import LLMClient
from app.agents.planner import PlannerAgent
from app.agents.researcher import ResearcherAgent
from app.agents.writer import WriterAgent
from app.memory.client import CogneeClient


async def main() -> None:
    cognee_client: CogneeClient = get_cognee_client()
    llm = LLMClient(model="gpt-4o-mini")

    async def emit(event: Dict[str, Any]) -> None:
        # Keep this very light: just show event type + agent
        print("EVENT:", event.get("type"), "agent=", event.get("agent"))

    dataset = "direct_agent_test"
    session_id = "direct-1"
    query = "Summarize AgentOS in 3 bullets."

    print("=== Direct agent harness (minimal) ===")
    print(f"Dataset: {dataset}")
    print(f"Session: {session_id}")
    print(f"Query:   {query}\n")

    # 1. Planner – but only keep the first subtask to control runtime
    planner = PlannerAgent(
        cognee=cognee_client,
        llm=llm,
        emit=emit,
        session_id=session_id,
    )
    print("--- PlannerAgent.run() ---")
    subtasks = await planner.run(query, dataset)
    if not subtasks:
        print("No subtasks returned, using original query as single subtask.")
        subtasks = [type("ST", (), {"id": "0", "query": query})()]

    first = subtasks[0]
    print(f"Using only subtask[0]: {first.query}\n")

    # 2. Researcher – single subtask
    print("--- ResearcherAgent.run() ---")
    researcher = ResearcherAgent(
        cognee=cognee_client,
        llm=llm,
        emit=emit,
        session_id=session_id,
    )

    findings = await researcher.run(first, dataset)
    print(f"\nResearcher produced {len(findings)} findings.")
    for f in findings[:3]:
        print("  Finding preview:", f.text[:200].replace("\n", " "), "...")

    # 3. Writer – synthesize answer
    print("\n--- WriterAgent.run() ---")
    writer = WriterAgent(
        cognee=cognee_client,
        llm=llm,
        emit=emit,
        session_id=session_id,
    )

    answer = await writer.run(query, findings, dataset, session_id=session_id)

    print("\n=== FINAL ANSWER (WriterAgent) ===\n")
    print(answer.text[:1200])  # truncate for readability
    print("\n=== Harness complete ===")


if __name__ == "__main__":
    # Add an overall timeout so it *must* finish
    asyncio.run(asyncio.wait_for(main(), timeout=120))