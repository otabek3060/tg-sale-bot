"""Telegram API bilan ishlash uchun yordamchilar."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from aiogram import Bot
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import Response, TelegramMethod
from aiogram.methods.base import TelegramType

log = logging.getLogger(__name__)
T = TypeVar("T")


class RetryAfterMiddleware(BaseRequestMiddleware):
    """Global: Telegram 429 (flood) qaytarsa — ko'rsatilgan vaqt kutib qayta yuboradi.
    429 da so'rov bajarilmagan bo'ladi, shuning uchun qayta yuborish xavfsiz (dublikat bo'lmaydi)."""

    def __init__(self, attempts: int = 3, max_wait: float = 60.0) -> None:
        self.attempts = attempts
        self.max_wait = max_wait

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method: TelegramMethod[TelegramType],
    ) -> Response[TelegramType]:
        for attempt in range(self.attempts):
            try:
                return await make_request(bot, method)
            except TelegramRetryAfter as e:
                if attempt == self.attempts - 1 or e.retry_after > self.max_wait:
                    raise
                log.warning("RetryAfter %ss on %s", e.retry_after, type(method).__name__)
                await asyncio.sleep(e.retry_after + 0.2)
        raise RuntimeError("unreachable")


async def quiet(coro: Awaitable[T]) -> T | None:
    """O'chirish/tahrirlashdagi kutilgan xatolarni jim yutadi
    (xabar topilmadi, 48 soatdan eski, o'zgarmagan, bot bloklangan)."""
    try:
        return await coro
    except (TelegramBadRequest, TelegramForbiddenError) as e:
        log.debug("quiet: %s", e)
        return None


async def gather_limited(limit: int, funcs: list[Callable[[], Awaitable[Any]]]) -> list[Any]:
    """Bir vaqtda `limit` tadan ko'p bo'lmagan parallel chaqiruv."""
    sem = asyncio.Semaphore(limit)

    async def run(f: Callable[[], Awaitable[Any]]) -> Any:
        async with sem:
            return await f()

    return await asyncio.gather(*(run(f) for f in funcs), return_exceptions=True)
