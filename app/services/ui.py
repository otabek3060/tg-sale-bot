"""«Toza chat» mexanizmi.

Har bir chat uchun bitta "ekran" xabari bor; uning ID si va turi Redis'da saqlanadi.
- Tur bir xil bo'lsa (matn→matn, rasm→rasm) — xabar tahrirlanadi.
- Tur o'zgarsa yoki tahrirlab bo'lmasa — eskisi o'chiriladi, yangisi yuboriladi.
- `persist()` — ekranni "doimiy" qiladi (havolali xabar keyingi render'da o'chib ketmasligi uchun).
"""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardMarkup, InputMediaPhoto, Message
from redis.asyncio import Redis

from app.utils.tg import quiet

log = logging.getLogger(__name__)
TTL = 48 * 3600  # Telegram 48 soatdan eski xabarni o'chirishga ruxsat bermaydi


class UI:
    def __init__(self, bot: Bot, redis: Redis) -> None:
        self.bot = bot
        self.redis = redis

    @staticmethod
    def _key(chat_id: int) -> str:
        return f"ui:{chat_id}"

    async def render(
        self,
        chat_id: int,
        text: str,
        markup: InlineKeyboardMarkup | None = None,
        *,
        photo: str | None = None,
        new: bool = False,
    ) -> int:
        """Ekranni ko'rsatadi. new=True — eskisini o'chirib, yangi xabar yuboradi (pastga tushadi)."""
        key = self._key(chat_id)
        state = await self.redis.hgetall(key)
        kind = "photo" if photo else "text"

        if state:
            old_id = int(state["id"])
            if not new and state.get("kind") == kind:
                try:
                    if photo:
                        await self.bot.edit_message_media(
                            chat_id=chat_id,
                            message_id=old_id,
                            media=InputMediaPhoto(media=photo, caption=text),
                            reply_markup=markup,
                        )
                    else:
                        await self.bot.edit_message_text(
                            chat_id=chat_id, message_id=old_id, text=text, reply_markup=markup
                        )
                    return old_id
                except TelegramBadRequest as e:
                    if "not modified" in e.message:
                        return old_id
                    log.debug("edit failed, resend: %s", e.message)
            await quiet(self.bot.delete_message(chat_id=chat_id, message_id=old_id))

        if photo:
            msg = await self.bot.send_photo(chat_id=chat_id, photo=photo, caption=text, reply_markup=markup)
        else:
            msg = await self.bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
        await self._remember(chat_id, msg, kind)
        return msg.message_id

    async def _remember(self, chat_id: int, msg: Message, kind: str) -> None:
        key = self._key(chat_id)
        async with self.redis.pipeline(transaction=True) as p:
            p.hset(key, mapping={"id": msg.message_id, "kind": kind})
            p.expire(key, TTL)
            await p.execute()

    async def persist(self, chat_id: int) -> None:
        """Joriy ekranni chatda qoldiramiz, keyingi render yangi xabar yuboradi."""
        await self.redis.delete(self._key(chat_id))

    async def notify(self, chat_id: int, text: str, markup: InlineKeyboardMarkup | None = None) -> bool:
        """Boshqa kontekstdan (admin harakati) foydalanuvchiga doimiy xabar.
        Eski ekran o'chadi, yangi xabar chatda qoladi. False — user botni bloklagan."""
        try:
            await self.render(chat_id, text, markup, new=True)
        except TelegramForbiddenError:
            return False
        await self.persist(chat_id)
        return True

    async def drop(self, message: Message) -> None:
        """Foydalanuvchi yuborgan keraksiz xabarni o'chirish (/start, noto'g'ri matn, admin tugmalari)."""
        await quiet(message.delete())
