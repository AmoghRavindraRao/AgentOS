"""Shared FastAPI dependencies."""

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.session import get_session
from app.memory.client import CogneeClient

# A single CogneeClient (and its write lock) is shared across requests.
_cognee_client = CogneeClient()


def get_cognee_client() -> CogneeClient:
    return _cognee_client


async def get_current_user(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> str:
    """Demo auth: a static Bearer token maps to the demo user.

    NOTE: This is intentionally minimal for the hackathon. There is no real
    authentication or per-user isolation beyond the static token — do not expose
    this service publicly without adding proper auth.
    """
    if authorization is None:
        # Day 1: allow unauthenticated calls so the graph stub is easy to poke.
        return settings.demo_user
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token != settings.demo_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing bearer token",
        )
    return settings.demo_user


DBSession = AsyncSession
__all__ = ["get_session", "get_current_user", "get_cognee_client", "DBSession"]
