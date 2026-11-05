"""To'lovlarni tasdiqlash / rad etish biznes mantig'i."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Config
from app.db.models import PaymentStatus
from app.db.repositories import misc, payments, users
from app.services.shop_settings import Shop, ShopSettings
from app.utils.timez import now_utc

log = logging.getLogger(__name__)


class LinkError(Exception):
    pass


@dataclass(slots=True)
class Link:
    url: str
    hours: int | None  # None — doimiy havola


class PaymentService:
    def __init__(
        self, bot: Bot, session_factory: async_sessionmaker[AsyncSession], shop: ShopSettings, config: Config
    ) -> None:
        self.bot = bot
        self.sf = session_factory
        self.shop = shop
        self.config = config

    async def make_link(self, shop: Shop, name: str) -> Link:
        if shop.link_mode == "invite":
            if not shop.channel_id:
                raise LinkError("Kanal ID sozlanmagan (⚙️ Sozlamalar → 📣 Kanal ID)")
            chat: int | str = shop.channel_id if shop.channel_id.startswith("@") else int(shop.channel_id)
            try:
                inv = await self.bot.create_chat_invite_link(
                    chat_id=chat,
                    name=name[:32],
                    member_limit=1,
                    expire_date=now_utc() + timedelta(hours=self.config.invite_link_hours),
                )
            except TelegramAPIError as e:
                raise LinkError(f"Telegram: {e.message}") from e
            return Link(inv.invite_link, self.config.invite_link_hours)
        if not shop.static_link:
            raise LinkError("Doimiy havola sozlanmagan (⚙️ Sozlamalar → 🔗 Doimiy havola)")
        return Link(shop.static_link, None)

    async def approve(self, payment_id: int, admin_id: int) -> tuple[int, Link] | None:
        """None — to'lov allaqachon boshqa admin tomonidan ko'rib chiqilgan.
        Havola yaratilmasa LinkError — to'lov o'zgarmaydi (pending bo'lib qoladi).

        1) Havola OLDINDAN yaratiladi — Telegram API chaqiruvi paytida DB ulanishi ushlanmaydi.
        2) BITTA tranzaksiya: atomik UPDATE ... WHERE status='pending' (faqat bitta admin yutadi)
           + havola + has_purchased + audit. Hammasi yoki hech narsa — yarim holat bo'lmaydi.
        3) Poygada yutqazgan admin yaratgan ortiqcha taklif havolasi bekor qilinadi."""
        async with self.sf() as s:
            pending = await payments.is_pending(s, payment_id)
        if not pending:
            return None
        shop = await self.shop.get()
        link = await self.make_link(shop, f"pay#{payment_id}")

        async with self.sf() as s:
            user_id = await payments.decide(s, payment_id, PaymentStatus.approved, admin_id)
            if user_id is not None:
                await payments.set_link(s, payment_id, link.url)
                await users.set_flag(s, user_id, has_purchased=True)
                await misc.audit(s, admin_id, "approve", payment_id=payment_id)
                await s.commit()
                return user_id, link
            await s.rollback()
        await self._revoke(shop, link)
        return None

    async def _revoke(self, shop: Shop, link: Link) -> None:
        if shop.link_mode != "invite" or not shop.channel_id:
            return
        chat: int | str = shop.channel_id if shop.channel_id.startswith("@") else int(shop.channel_id)
        try:
            await self.bot.revoke_chat_invite_link(chat_id=chat, invite_link=link.url)
        except TelegramAPIError:
            log.warning("Ortiqcha havolani bekor qilib bo'lmadi: %s", link.url)

    async def reject(self, payment_id: int, admin_id: int, reason: str) -> int | None:
        async with self.sf() as s:
            user_id = await payments.decide(s, payment_id, PaymentStatus.rejected, admin_id, reason[:256])
            if user_id is None:
                await s.rollback()
                return None
            await misc.audit(s, admin_id, "reject", payment_id=payment_id, reason=reason[:256])
            await s.commit()
        return user_id

    async def link_for_user(self, user_id: int) -> Link | None:
        """Xarid qilgan foydalanuvchiga havolani qayta berish."""
        shop = await self.shop.get()
        async with self.sf() as s:
            last = await payments.last_approved(s, user_id)
        if last is None:
            return None
        link = await self.make_link(shop, f"pay#{last.id}-re")
        if shop.link_mode == "invite":
            async with self.sf() as s:
                await payments.set_link(s, last.id, link.url)
                await s.commit()
        return link
