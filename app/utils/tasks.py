from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

log = logging.getLogger(__name__)


class BackgroundTasks:
    """Fon vazifalari: handler'ni ushlab turmaydi, lekin havolalar saqlanadi (GC o'chirib yubormasligi uchun)
    va to'xtashda tugashini kutamiz."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()

    def spawn(self, coro: Coroutine[Any, Any, Any], name: str | None = None) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._done)
        return task

    def _done(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            log.error("Background task %s failed", task.get_name(), exc_info=task.exception())

    async def wait(self, timeout: float = 30.0) -> None:
        if self._tasks:
            await asyncio.wait(set(self._tasks), timeout=timeout)

    def __len__(self) -> int:
        return len(self._tasks)
