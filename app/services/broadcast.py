"""Ommaviy xabar (broadcast). Telegram limiti ~30 xabar/s — biz `broadcast_rate` (25/s) bilan
bir tekis yuboramiz, javobni kutmasdan keyingisini rejalashtiramiz (sliding window)."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repositories import users
from app.utils.tasks import BackgroundTasks

log = logging.getLogger(__name__)
LOCK = "lock:broadcast"


@dataclass
class Report:
    sent: int = 0
    blocked: int = 0
    failed: int = 0
    blocked_ids: list[int] = field(default_factory=list)


class Broadcaster:
    def __init__(
        self,
        bot: Bot,
        redis: Redis,
        session_factory: async_sessionmaker[AsyncSession],
        tasks: BackgroundTasks,
        rate: int,
    ) -> None:
        self.bot = bot
        self.redis = redis
        self.sf = session_factory
        self.tasks = tasks
        self.rate = max(1, rate)

    async def is_running(self) -> bool:
        return bool(await self.redis.exists(LOCK))

    async def start(self, admin_id: int, from_chat_id: int, message_id: int, audience: str) -> bool:
        if not await self.redis.set(LOCK, str(admin_id), nx=True, ex=12 * 3600):
            return False
        self.tasks.spawn(self._run(admin_id, from_chat_id, message_id, audience), name="broadcast")
        return True

    async def _send(self, uid: int, from_chat_id: int, message_id: int, rep: Report) -> None:
        try:
            await self.bot.copy_message(chat_id=uid, from_chat_id=from_chat_id, message_id=message_id)
            rep.sent += 1
        except TelegramForbiddenError:
            rep.blocked += 1
            rep.blocked_ids.append(uid)
        except (TelegramBadRequest, TelegramRetryAfter) as e:
            rep.failed += 1
            log.debug("broadcast to %s failed: %s", uid, e)
        except Exception:  # noqa: BLE001 - bitta user butun broadcast'ni to'xtatmasin
            rep.failed += 1
            log.exception("broadcast to %s crashed", uid)

    async def _run(self, admin_id: int, from_chat_id: int, message_id: int, audience: str) -> Report:
        rep = Report()
        interval = 1 / self.rate
        window = asyncio.Semaphore(self.rate)
        pending: set[asyncio.Task[None]] = set()
        last_id = -(2**63)
        try:
            while True:
                async with self.sf() as s:
                    batch = await users.audience_batch(s, audience, last_id)
                if not batch:
                    break
                last_id = batch[-1]
                for uid in batch:
                    await window.acquire()
                    t = asyncio.create_task(self._send(uid, from_chat_id, message_id, rep))
                    pending.add(t)
                    t.add_done_callback(lambda tt: (pending.discard(tt), window.release()))
                    await asyncio.sleep(interval)
                if rep.blocked_ids:
                    ids, rep.blocked_ids = rep.blocked_ids, []
                    async with self.sf() as s:
                        await users.mark_blocked(s, ids)
                        await s.commit()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            if rep.blocked_ids:
                async with self.sf() as s:
                    await users.mark_blocked(s, rep.blocked_ids)
                    await s.commit()
        finally:
            await self.redis.delete(LOCK)
            try:
                await self.bot.send_message(
                    admin_id,
                    "📢 <b>Xabar yuborish yakunlandi</b>\n\n"
                    f"✅ Yuborildi: {rep.sent}\n🚫 Botni bloklagan: {rep.blocked}\n⚠️ Xato: {rep.failed}",
                )
            except Exception:  # noqa: BLE001
                log.exception("broadcast report failed")
        return rep
