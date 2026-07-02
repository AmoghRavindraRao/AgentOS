"""
verify_graph.py — Check Cognee graph snapshot for a given domain.

Usage:
    - Set DOMAIN_ID below (from agentos.db or seed_domain.py output).
    - cd backend
    - uv run python verify_graph.py
"""

import asyncio
import httpx

BASE = "http://localhost:8000/api/v1"
HEADERS: dict = {}

# Paste your domain id here (from seed_domain.py or a DB query):
DOMAIN_ID = "60b3b54e52054aa68ecff3e823517913"


async def verify_graph() -> None:
    async with httpx.AsyncClient(base_url=BASE, headers=HEADERS, timeout=30) as client:
        r = await client.get(f"/domains/{DOMAIN_ID}/graph")
        if r.status_code == 404:
            print(f"⚠️  Domain {DOMAIN_ID} not found. Check DOMAIN_ID.")
            return
        r.raise_for_status()
        data = r.json()
        nodes = data.get("nodes", [])
        links = data.get("links", [])

        print("\n📊 Graph snapshot:")
        print(f"  Nodes: {len(nodes)}")
        print(f"  Links: {len(links)}")

        if not nodes:
            print("  ⚠️  No nodes yet — Cognee may still be indexing or this domain has only a few ingests.")
            return

        print("\n  Sample nodes:")
        for n in nodes[:5]:
            print(f"    - [{n.get('group','Entity')}] {n.get('label','(no label)')} (id={n.get('id')})")

        if links:
            print("\n  Sample links:")
            for e in links[:5]:
                print(f"    - {e.get('source')} --{e.get('relation','RELATED_TO')}--> {e.get('target')}")

        print("\n✅ Graph endpoint working for this domain.")


if __name__ == "__main__":
    asyncio.run(verify_graph())