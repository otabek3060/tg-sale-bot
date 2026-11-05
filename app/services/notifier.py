"""Adminlarga xabar tarqatish (fan-out) va ularning xabarlarini sinxron yangilash."""
from __future__ import annotations

import logging
from html import escape

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import keyboards as kb
from app.db.models import Payment, User
from app.db.repositories import payments
from app.services.access import Access
from app.texts import uz
from app.utils.tg import gather_limited, quiet
from app.utils.timez import fmt

log = logging.getLogger(__name__)
PARALLEL = 10


def admin_caption(p: Payment, u: User) -> str:
    uname = f" · @{escape(u.username)}" if u.username else ""
    text = (
        f"🧾 <b>To'lov #{p.id}</b>\n"
        f"👤 Ism: {escape(u.full_name)}\n"
        f"🆔 ID: <code>{u.telegram_id}</code>{uname}\n"
        f"💰 Summa: {uz.money(p.amount)}\n"
        f"🕒 {fmt(p.created_at)}"
    )
    if p.duplicate_of and p.duplicate_of != p.id:
        text += f"\n\n⚠️ <b>Diqqat:</b> bu chek avval #{p.duplicate_of} to'lovda yuborilgan!"
    return text


def admin_label(user: object) -> str:
    username = getattr(user, "username", None)
    return f"@{username}" if username else escape(getattr(user, "full_name", "") or str(getattr(user, "id", "")))


class Notifier:
    def __init__(self, bot: Bot, session_factory: async_sessionmaker[AsyncSession], access: Access) -> None:
        self.bot = bot
        self.sf = session_factory
        self.access = access

    async def _send_receipt(self, chat_id: int, p: Payment, caption: str, markup: InlineKeyboardMarkup) -> Message:
        if p.file_type == "photo":
            return await self.bot.send_photo(chat_id=chat_id, photo=p.file_id, caption=caption, reply_markup=markup)
        return await self.bot.send_document(chat_id=chat_id, document=p.file_id, caption=caption, reply_markup=markup)

    async def new_payment(self, p: Payment, u: User) -> None:
        """Chekni barcha adminlarga parallel yuboradi va xabar ID larini saqlaydi.
        Obyektlar handler'dan to'g'ridan-to'g'ri keladi — DB'dan qayta o'qimaymiz."""
        payment_id = p.id
        caption, markup = admin_caption(p, u), kb.review(p.id)
        admin_ids = sorted(await self.access.admin_ids())

        async def send(aid: int) -> tuple[int, int]:
            msg = await self._send_receipt(aid, p, caption, markup)
            return aid, msg.message_id

        results = await gather_limited(PARALLEL, [lambda a=a: send(a) for a in admin_ids])
        ok = [r for r in results if isinstance(r, tuple)]
        for aid, r in zip(admin_ids, results, strict=True):
            if isinstance(r, BaseException):
                log.warning("Receipt #%s not delivered to admin %s: %s", payment_id, aid, r)
        async with self.sf() as s:
            await payments.save_admin_messages(s, payment_id, ok)
            await s.commit()

    async def send_receipt_to(self, admin_id: int, payment_id: int) -> bool:
        """Kutilayotganlar ro'yxatidan chekni bitta adminga qayta ochish."""
        async with self.sf() as s:
            row = await payments.get_with_user(s, payment_id)
        if row is None:
            return False
        p, u = row
        msg = await self._send_receipt(admin_id, p, admin_caption(p, u), kb.review(p.id))
        async with self.sf() as s:
            await payments.save_admin_messages(s, payment_id, [(admin_id, msg.message_id)])
            await s.commit()
        return True

    async def finalize(
        self, payment_id: int, status_line: str, extra: dict[int, InlineKeyboardMarkup] | None = None
    ) -> None:
        """Barcha adminlardagi chek xabarini yangilaydi: tugmalar olib tashlanadi, natija yoziladi."""
        async with self.sf() as s:
            row = await payments.get_with_user(s, payment_id)
            targets = await payments.admin_messages(s, payment_id)
        if row is None:
            return
        caption = admin_caption(*row) + "\n\n" + status_line
        extra = extra or {}

        await gather_limited(
            PARALLEL,
            [
                lambda a=a, m=m: quiet(
                    self.bot.edit_message_caption(
                        chat_id=a, message_id=m, caption=caption, reply_markup=extra.get(a)
                    )
                )
                for a, m in targets
            ],
        )

    async def to_admins(self, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
        ids = await self.access.admin_ids()
        await gather_limited(
            PARALLEL, [lambda a=a: quiet(self.bot.send_message(a, text, reply_markup=markup)) for a in ids]
        )
