"""FastAPI application entry point + lifespan.

Day 1: app DB init, CORS, health check, and the domains router (create/list +
brain-graph stub). Run with:

    uvicorn app.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import domains, sessions, stream, sources
from app.db.session import init_db
from app.memory.cognee_lifecycle import close_cognee_async_resources


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    try:
        yield
    finally:
        await close_cognee_async_resources()


app = FastAPI(title="AgentOS", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(domains.router)
app.include_router(sessions.router)
app.include_router(stream.router)
app.include_router(sources.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
