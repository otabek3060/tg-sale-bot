from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repositories import users
from app.services.access import ADMINS_KEY, BANNED_KEY, Access
from app.texts import uz

log = logging.getLogger("app.update")
Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class TimingMiddleware(BaseMiddleware):
    """Har bir update ishlash vaqtini o'lchaydi; sekinlarini WARNING bilan yozadi."""

    def __init__(self, slow_ms: float = 500) -> None:
        self.slow_ms = slow_ms

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        t0 = time.perf_counter()
        try:
            return await handler(event, data)
        finally:
            ms = round((time.perf_counter() - t0) * 1000, 1)
            user = data.get("event_from_user")
            extra = {"update_id": getattr(event, "update_id", None), "user_id": user.id if user else None, "ms": ms}
            if ms >= self.slow_ms:
                log.warning("slow update", extra=extra)
            else:
                log.debug("update", extra=extra)


class GuardMiddleware(BaseMiddleware):
    """Bitta Redis round-trip (pipeline) bilan:
    admin/ban tekshiruvi, anti-flood (sekundiga N ta), foydalanuvchi faolligini yangilash (5 daqiqada 1 marta)."""

    def __init__(
        self, redis: Redis, access: Access, session_factory: async_sessionmaker[AsyncSession], rate: int
    ) -> None:
        self.redis = redis
        self.access = access
        self.sf = session_factory
        self.rate = rate

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user = data.get("event_from_user")
        chat = data.get("event_chat")
        if user is None or user.is_bot:
            return await handler(event, data)
        if chat is not None and chat.type != "private":
            return None  # bot faqat shaxsiy chatda ishlaydi

        uid = str(user.id)
        rl_key = f"rl:{uid}"
        async with self.redis.pipeline(transaction=False) as p:
            p.sismember(ADMINS_KEY, uid)
            p.exists(ADMINS_KEY)
            p.sismember(BANNED_KEY, uid)
            p.incr(rl_key)
            p.expire(rl_key, 1, nx=True)
            p.set(f"seen:{uid}", "1", nx=True, ex=300)
            in_admins, admins_loaded, banned, hits, _, first_seen = await p.execute()

        if self.access.is_owner(user.id) or in_admins:
            is_admin = True
        elif not admins_loaded:
            is_admin = await self.access.is_admin(user.id)
        else:
            is_admin = False
        data["is_admin"] = is_admin

        if not is_admin:
            if banned:
                return None
            if hits > self.rate:
                if isinstance(event, Update) and event.callback_query:
                    with suppress(Exception):
                        await event.callback_query.answer(uz.TOO_MANY)
                return None

        if first_seen and not _is_start(event):
            # /start o'zi upsert qiladi; qolganlarda faollikni 5 daqiqada bir yangilaymiz
            async with self.sf() as s:
                await users.upsert(s, user)
                await s.commit()
        return await handler(event, data)


def _is_start(event: TelegramObject) -> bool:
    return bool(
        isinstance(event, Update) and event.message and event.message.text and event.message.text.startswith("/start")
    )


class DbSessionMiddleware(BaseMiddleware):
    """Har update uchun lazy AsyncSession: ulanish faqat birinchi so'rovda olinadi
    va commit/rollback'dan keyin darhol pulga qaytadi."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.sf = session_factory

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        async with self.sf() as session:
            data["session"] = session
            return await handler(event, data)
