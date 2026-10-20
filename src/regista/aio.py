"""Running coroutines from synchronous code, safely inside or outside an event loop."""

from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Awaitable
from typing import Any


def run_sync(coro: Awaitable[Any]) -> Any:
    """Run a coroutine to completion from synchronous code, whether or not an event loop is running.

    Agents are synchronous (the orchestrator calls ``handle``), but the API and the Agent Framework
    workflow call into them from a running loop, where ``asyncio.run`` refuses to start. In that
    case the coroutine runs on a fresh loop in a worker thread."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()
