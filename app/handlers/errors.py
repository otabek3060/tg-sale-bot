from __future__ import annotations

import logging
from contextlib import suppress
from html import escape

from aiogram import Bot, Router
from aiogram.types import ErrorEvent
from redis.asyncio import Redis

from app.config import Config
from app.texts import uz

router = Router(name="errors")
log = logging.getLogger(__name__)


@router.errors()
async def on_error(event: ErrorEvent, bot: Bot, redis: Redis, config: Config) -> bool:
    upd = event.update
    log.error("Unhandled error in update %s", upd.update_id, exc_info=event.exception)

    # Foydalanuvchiga xabar
    with suppress(Exception):
        if upd.callback_query:
            await upd.callback_query.answer(uz.TECH_ERROR, show_alert=True)
        elif upd.message:
            await bot.send_message(upd.message.chat.id, uz.TECH_ERROR)

    # Egasiga qisqa xabar — 5 daqiqada ko'pi bilan 1 marta (spam bo'lmasligi uchun)
    with suppress(Exception):
        if await redis.set("lock:error_notify", "1", nx=True, ex=300):
            await bot.send_message(
                config.owner_id,
                f"🔥 <b>Botda xato</b> (update {upd.update_id})\n<code>{escape(repr(event.exception))[:3500]}</code>",
            )
    return True
