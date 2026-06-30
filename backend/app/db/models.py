"""SQLModel ORM models mirroring schema.sql.

These are the only coordination tables AgentOS owns. Cognee owns the graph,
vector, and session memory — these tables just map app concepts (domains,
sessions, sources, confidence) onto Cognee dataset names and data ids.
"""

import time
import uuid
from typing import Optional

from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> float:
    return time.time()


class Domain(SQLModel, table=True):
    __tablename__ = "domains"

    id: str = Field(default_factory=_uuid, primary_key=True)
    user: str = Field(index=True)
    slug: str
    title: str
    # "u_{safe(user)}_d_{safe(slug)}" — the only coupling point to Cognee.
    dataset_name: str = Field(unique=True, index=True)
    created_at: float = Field(default_factory=_now)


class Session(SQLModel, table=True):
    __tablename__ = "sessions"

    id: str = Field(default_factory=_uuid, primary_key=True)
    domain_id: str = Field(index=True, foreign_key="domains.id")
    query: str
    # planning | researching | writing | improving | complete | error
    status: str = "planning"
    output: Optional[str] = None
    created_at: float = Field(default_factory=_now)
    completed_at: Optional[float] = None


class Source(SQLModel, table=True):
    __tablename__ = "sources"

    id: str = Field(default_factory=_uuid, primary_key=True)
    domain_id: str = Field(index=True, foreign_key="domains.id")
    # result.items[0]["id"] from remember(); handle for forget(data_id=...)
    cognee_data_id: Optional[str] = None
    kind: str  # web | url | pdf | text
    uri: str
    title: Optional[str] = None
    added_at: float = Field(default_factory=_now)


class Confidence(SQLModel, table=True):
    __tablename__ = "confidence"

    id: str = Field(default_factory=_uuid, primary_key=True)
    domain_id: str = Field(index=True, foreign_key="domains.id")
    node_ref: str
    score: float = 0.5  # [0.0, 1.0]
    upvotes: int = 0
    last_seen: float = Field(default_factory=_now)
    forgotten: int = 0  # 1 = filtered from recall results
