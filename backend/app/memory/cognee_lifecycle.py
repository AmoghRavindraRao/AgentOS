"""Lifecycle cleanup for Cognee resources owned outside this app."""

from __future__ import annotations

import asyncio
import inspect
from importlib import import_module
from types import ModuleType
from typing import Any


async def close_cognee_async_resources() -> None:
    """Best-effort shutdown for Cognee async resources.

    Cognee currently keeps a process-wide aiohttp session for telemetry. If any
    telemetry work was scheduled before local-dev mode was applied, drain it and
    close the private session before the event loop shuts down.
    """
    await _drain_cognee_telemetry_tasks()
    await _close_cognee_telemetry_session()


async def _drain_cognee_telemetry_tasks(timeout: float = 1.0) -> None:
    current = asyncio.current_task()
    tasks = [
        task
        for task in asyncio.all_tasks()
        if task is not current and _is_cognee_telemetry_task(task)
    ]
    if not tasks:
        return

    _, pending = await asyncio.wait(tasks, timeout=timeout)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


def _is_cognee_telemetry_task(task: asyncio.Task[Any]) -> bool:
    coro = task.get_coro()
    name = getattr(coro, "__qualname__", "") or getattr(coro, "__name__", "")
    if "_send_telemetry_request" in name:
        return True

    code = getattr(coro, "cr_code", None)
    return getattr(code, "co_name", "") == "_send_telemetry_request"


async def _close_cognee_telemetry_session() -> None:
    try:
        utils = import_module("cognee.shared.utils")
    except Exception:  # noqa: BLE001
        return

    session = getattr(utils, "_telemetry_session", None)
    if session is None:
        _reset_telemetry_state(utils)
        return

    try:
        if not getattr(session, "closed", False):
            close_result = session.close()
            if inspect.isawaitable(close_result):
                await close_result
    finally:
        _reset_telemetry_state(utils)


def _reset_telemetry_state(utils: ModuleType) -> None:
    for attr in (
        "_telemetry_session",
        "_telemetry_session_loop",
        "_telemetry_session_lock",
        "_telemetry_session_lock_loop",
    ):
        if hasattr(utils, attr):
            setattr(utils, attr, None)
