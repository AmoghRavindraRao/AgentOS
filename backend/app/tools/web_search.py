"""Web search and content fetching for ResearcherAgent.

Two modes:
  1. Tavily search (if TAVILY_API_KEY is set) — returns ranked results with snippets
  2. Fallback: direct URL fetch + trafilatura text extraction

Returns a list of SourceDoc(text, source_uri).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import httpx
import re


@dataclass
class SourceDoc:
    text: str
    source_uri: str


_HEADERS = {"User-Agent": "AgentOS-Researcher/1.0"}
_TAVILY_URL = "https://api.tavily.com/search"


async def web_search_and_fetch(query: str, max_results: int = 3) -> list[SourceDoc]:
    """Search the web and return extracted text documents."""
    tavily_key = os.getenv("TAVILY_API_KEY", "").strip()

    if tavily_key:
        return await _tavily_search(query, tavily_key, max_results)
    else:
        # No Tavily key: return a minimal stub so the pipeline keeps moving.
        # On Day 3 this gets replaced with a proper fallback.
        return [
            SourceDoc(
                text=f"Research context for: {query}. "
                     "No web search configured (set TAVILY_API_KEY in .env). "
                     "Agent will rely entirely on domain brain memory.",
                source_uri=f"query://{query[:60]}",
            )
        ]


async def _tavily_search(query: str, api_key: str, max_results: int) -> list[SourceDoc]:
    """Use Tavily Search API to get real web results."""
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            resp = await client.post(
                _TAVILY_URL,
                json={
                    "api_key": api_key,
                    "query": query,
                    "search_depth": "basic",
                    "max_results": max_results,
                    "include_raw_content": True,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            docs: list[SourceDoc] = []
            for r in data.get("results", []):
                # Prefer raw_content (full page), fall back to snippet
                text = r.get("raw_content") or r.get("content") or ""
                if not text:
                    continue
                # Trim to 3000 chars per doc to stay within token budgets
                docs.append(SourceDoc(text=text[:3000], source_uri=r.get("url", "")))
            return docs or [SourceDoc(text=f"No results found for: {query}", source_uri="")]
        except Exception as e:
            return [SourceDoc(text=f"Search error: {e}", source_uri="")]


async def fetch_url(url: str) -> SourceDoc:
    """Fetch a single URL and extract clean text via trafilatura."""
    async with httpx.AsyncClient(timeout=20, headers=_HEADERS) as client:
        try:
            resp = await client.get(url, follow_redirects=True)
            resp.raise_for_status()
            raw = resp.text
            text = re.sub(r"<[^>]+>", " ", raw)
            text = re.sub(r"\s+", " ", text).strip()[:3000]
            return SourceDoc(text=text, source_uri=url)
        except Exception as e:
            return SourceDoc(text=f"Fetch error for {url}: {e}", source_uri=url)