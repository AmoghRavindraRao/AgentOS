"""Thin async OpenAI wrapper used by all three agents.

Keeps provider details out of agent logic. To swap to another provider,
replace this file — nothing else changes.
"""
from __future__ import annotations

import os
from openai import AsyncOpenAI


class LLMClient:
    def __init__(self, model: str = "gpt-4o-mini") -> None:
        self._model = model
        self._client = AsyncOpenAI(api_key=os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))

    async def complete(self, system: str, user: str) -> str:
        """Single-turn chat completion. Returns the assistant message text."""
        resp = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.3,
        )
        return resp.choices[0].message.content or ""