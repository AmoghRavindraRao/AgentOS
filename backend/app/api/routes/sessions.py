"""Session routes."""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_cognee_client, get_current_user
from app.db.models import Domain, Session as SessionModel
from app.db.session import get_session
from app.memory.client import CogneeClient
from app.orchestrator.session import SessionOrchestrator

router = APIRouter(prefix="/api/v1", tags=["sessions"])


class RunRequest(BaseModel):
    query: str


class SessionOut(BaseModel):
    id: str
    domain_id: str
    query: str
    status: str
    output: str | None = None


@router.post("/domains/{domain_id}/run", status_code=202)
async def run_session(
    domain_id: str,
    body: RunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_session),
    cognee_client: CogneeClient = Depends(get_cognee_client),
    user: str = Depends(get_current_user),
) -> dict:
    domain = await db.get(Domain, domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail="Domain not found")
    if domain.user != user:
        raise HTTPException(status_code=403, detail="Not your domain")

    # Generate session_id HERE so we can return it immediately
    session_id = uuid.uuid4().hex
    orchestrator = SessionOrchestrator(cognee=cognee_client)

    background_tasks.add_task(orchestrator.run_session, domain, body.query, session_id)

    return {"session_id": session_id, "status": "started", "domain_id": domain_id}


@router.get("/sessions/{session_id}", response_model=SessionOut)
async def get_session_status(
    session_id: str,
    db: AsyncSession = Depends(get_session),
    user: str = Depends(get_current_user),
) -> SessionModel:
    row = await db.get(SessionModel, session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return row