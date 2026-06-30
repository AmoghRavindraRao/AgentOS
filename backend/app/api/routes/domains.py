"""Domain routes.

Day 1 scope: minimal create/list plus the brain-graph stub
(GET /domains/{id}/graph) backed by get_graph_engine().get_graph_data().
Sessions, sources, and SSE land on Day 2+.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_cognee_client, get_current_user
from app.db.models import Domain
from app.db.session import get_session
from app.memory.client import CogneeClient
from app.memory.domain_manager import DomainManager

router = APIRouter(prefix="/api/v1/domains", tags=["domains"])

_domains = DomainManager()


class CreateDomain(BaseModel):
    slug: str
    title: str


class DomainOut(BaseModel):
    id: str
    user: str
    slug: str
    title: str
    dataset_name: str


@router.get("", response_model=list[DomainOut])
async def list_domains(
    user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> list[Domain]:
    rows = (await db.execute(select(Domain).where(Domain.user == user))).scalars().all()
    return list(rows)


@router.post("", response_model=DomainOut, status_code=201)
async def create_domain(
    body: CreateDomain,
    user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> Domain:
    dataset_name = _domains.dataset_name(user, body.slug)
    domain = Domain(
        user=user, slug=body.slug, title=body.title, dataset_name=dataset_name
    )
    db.add(domain)
    await db.commit()
    await db.refresh(domain)
    return domain


@router.get("/{domain_id}/graph")
async def get_domain_graph(
    domain_id: str,
    db: AsyncSession = Depends(get_session),
    cognee_client: CogneeClient = Depends(get_cognee_client),
) -> dict:
    """Brain-graph node/edge dump for react-force-graph-2d.

    Day 1 stub: returns the full embedded-graph snapshot. Domain-scoped
    filtering by dataset_name is wired up on Day 4 once nodes carry the
    dataset tag consistently.
    """
    domain = await db.get(Domain, domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail="Domain not found")
    try:
        return await cognee_client.get_graph_snapshot(domain.dataset_name)
    except Exception:
        # Empty/uninitialized graph is normal on Day 1 — return an empty graph
        # rather than a 500 so the frontend shell renders.
        return {"nodes": [], "links": []}
