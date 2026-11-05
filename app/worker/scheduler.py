"""Davriy vazifalar. Bir nechta instansiya ishlasa ham Redis lock tufayli faqat bittasi bajaradi."""
from __future__ import annotations

import asyncio
import contextlib
import logging

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import keyboards as kb
from app.callbacks import AdmCb
from app.db.repositories import payments
from app.services.notifier import Notifier

log = logging.getLogger(__name__)


async def remind_overdue(sf: async_sessionmaker[AsyncSession], notifier: Notifier, minutes: int) -> int:
    async with sf() as s:
        ids = await payments.overdue_unreminded(s, minutes)
        if ids:
            await payments.mark_reminded(s, ids)
            await s.commit()
    if ids:
        await notifier.to_admins(
            f"⏰ <b>{len(ids)} ta to'lov {minutes} daqiqadan beri tekshirilmagan!</b>\n"
            "Foydalanuvchilarga 1 soat ichida javob berish va'da qilingan.",
            kb.rows([("⏳ Kutilayotganlarni ochish", AdmCb(s="sales", a="pending"))]),
        )
    return len(ids)


async def scheduler_loop(
    redis: Redis,
    sf: async_sessionmaker[AsyncSession],
    notifier: Notifier,
    minutes: int,
    stop: asyncio.Event,
    period: float = 60.0,
) -> None:
    while not stop.is_set():
        try:
            if await redis.set("lock:scheduler", "1", nx=True, ex=int(period) - 5):
                await remind_overdue(sf, notifier, minutes)
        except Exception:  # noqa: BLE001
            log.exception("scheduler iteration failed")
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=period)
