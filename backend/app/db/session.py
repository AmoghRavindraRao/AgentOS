"""Async SQLite session factory + schema initialization.

We create tables from the SQLModel metadata (which mirrors schema.sql). The raw
schema.sql is kept alongside as the canonical reference / migration seed.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from app.config import get_settings

# Import models so they register on SQLModel.metadata before create_all.
from app.db import models  # noqa: F401

_settings = get_settings()

engine = create_async_engine(_settings.app_database_url, echo=False, future=True)

async_session_factory = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def init_db() -> None:
    """Create all coordination tables if they do not exist."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async DB session."""
    async with async_session_factory() as session:
        yield session
