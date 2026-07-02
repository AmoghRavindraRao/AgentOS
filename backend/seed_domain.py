"""
seed_domain.py — Stress test with real research papers via URL ingest.

Uses arXiv abstract pages (HTML) so trafilatura can extract clean text.
Run after the server is up:
    cd backend
    uv run python seed_domain.py
"""

import asyncio
import httpx

BASE = "http://localhost:8000/api/v1"
HEADERS: dict = {}

DOMAIN_SLUG = "ai-safety-papers"
DOMAIN_TITLE = "AI Safety Research Papers"

# Real arXiv papers — abstract HTML pages (freely accessible, no auth needed)
SOURCES = [
    {
        "title": "Attention Is All You Need (Transformer)",
        "kind": "url",
        "uri": "https://arxiv.org/abs/1706.03762",
    },
    {
        "title": "RLHF — Training language models to follow instructions (InstructGPT)",
        "kind": "url",
        "uri": "https://arxiv.org/abs/2203.02155",
    },
    {
        "title": "Constitutional AI: Harmlessness from AI Feedback",
        "kind": "url",
        "uri": "https://arxiv.org/abs/2212.08073",
    },
    {
        "title": "Reward Hacking and Specification Gaming in AI",
        "kind": "url",
        "uri": "https://arxiv.org/abs/1906.01820",
    },
    {
        "title": "Chain-of-Thought Prompting Elicits Reasoning in LLMs",
        "kind": "url",
        "uri": "https://arxiv.org/abs/2201.11903",
    },
]


async def seed() -> str:
    async with httpx.AsyncClient(base_url=BASE, headers=HEADERS, timeout=120) as client:

        # 1. Find or create domain
        print(f"Looking up domain slug='{DOMAIN_SLUG}'...")
        r = await client.get("/domains")
        r.raise_for_status()
        domains = r.json()
        domain = next((d for d in domains if d["slug"] == DOMAIN_SLUG), None)

        if domain:
            print("  ✅ Domain already exists, reusing.")
        else:
            print("  Creating domain...")
            r = await client.post(
                "/domains",
                json={"slug": DOMAIN_SLUG, "title": DOMAIN_TITLE},
            )
            r.raise_for_status()
            domain = r.json()
            print("  ✅ Domain created.")

        domain_id = domain["id"]
        dataset_name = domain["dataset_name"]
        print(f"  domain_id    = {domain_id}")
        print(f"  dataset_name = {dataset_name}")

        # 2. Ingest each source
        source_ids: list[str] = []
        for i, src in enumerate(SOURCES, 1):
            print(f"\nIngesting {i}/{len(SOURCES)}: '{src['title']}'")
            print(f"  URL: {src['uri']}")
            r = await client.post(
                "/sources",
                json={
                    "domain_id": domain_id,
                    "kind": src["kind"],
                    "uri": src["uri"],
                    "title": src["title"],
                },
                timeout=60,
            )
            if r.status_code not in (200, 201):
                print(f"  ⚠️  Failed: {r.status_code} — {r.text[:200]}")
                continue
            result = r.json()
            source_ids.append(result["id"])
            print(f"  ✅ source_id      = {result['id']}")
            print(f"  ✅ cognee_data_id = {result.get('cognee_data_id')}")

        print("\n" + "=" * 60)
        print(f"✅ Seeded domain='{DOMAIN_SLUG}' with {len(source_ids)}/{len(SOURCES)} sources")
        print(f"   domain_id = {domain_id}")
        print(f"   dataset_name = {dataset_name}")
        print("\nUpdate DOMAIN_ID in verify_graph.py and verify_pipeline.py:")
        print(f"   DOMAIN_ID = \"{domain_id}\"")
        print("=" * 60)
        return domain_id


if __name__ == "__main__":
    asyncio.run(seed())
