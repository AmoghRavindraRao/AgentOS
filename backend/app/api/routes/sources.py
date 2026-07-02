"""Sources routes — ingest documents into a domain brain."""
from __future__ import annotations

import httpx
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_cognee_client, get_current_user
from app.db.models import Domain, Source
from app.db.session import get_session
from app.memory.client import CogneeClient

router = APIRouter(prefix="/api/v1/sources", tags=["sources"])


class CreateSource(BaseModel):
    domain_id: str
    kind: str          # "text" | "url" | "web" | "pdf"
    uri: str           # raw text content when kind="text", URL otherwise
    title: str | None = None


class SourceOut(BaseModel):
    id: str
    domain_id: str
    kind: str
    uri: str
    title: str | None
    cognee_data_id: str | None
    added_at: float


async def _load_content(kind: str, uri: str) -> str:
    """Resolve a source to plain text."""
    if kind == "text":
        return uri  # uri IS the content for text blobs
    if kind in ("url", "web"):
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(uri)
            resp.raise_for_status()
            return resp.text[:8000]  # cap to avoid huge ingests
    raise ValueError(f"Unsupported kind: {kind}")


@router.post("", response_model=SourceOut, status_code=201)
async def create_source(
    body: CreateSource,
    db: AsyncSession = Depends(get_session),
    cognee_client: CogneeClient = Depends(get_cognee_client),
    user: str = Depends(get_current_user),
) -> Source:
    domain = await db.get(Domain, body.domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail="Domain not found")
    if domain.user != user:
        raise HTTPException(status_code=403, detail="Not your domain")

    # Load and ingest into Cognee
    content = await _load_content(body.kind, body.uri)
    cognee_data_id = await cognee_client.ingest(domain.dataset_name, content)

    # Persist to app DB
    source = Source(
        domain_id=body.domain_id,
        kind=body.kind,
        uri=body.uri if body.kind != "text" else "(text blob)",
        title=body.title,
        cognee_data_id=cognee_data_id,
        added_at=time.time(),
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return source


@router.delete("/{source_id}", status_code=204)
async def delete_source(
    source_id: str,
    db: AsyncSession = Depends(get_session),
    cognee_client: CogneeClient = Depends(get_cognee_client),
    user: str = Depends(get_current_user),
) -> None:
    source = await db.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    domain = await db.get(Domain, source.domain_id)
    if domain.user != user:
        raise HTTPException(status_code=403, detail="Not your domain")

    if source.cognee_data_id is None:
        raise HTTPException(status_code=400, detail="Source not yet indexed, cannot forget")

    await cognee_client.forget_source(domain.dataset_name, source.cognee_data_id)
    await db.delete(source)
    await db.commit()