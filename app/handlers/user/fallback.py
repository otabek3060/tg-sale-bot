"""Eng oxirgi router: tushunilmagan xabarlar o'chiriladi, foydalanuvchi asosiy ekranga qaytadi."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import users
from app.handlers.user.common import show_home
from app.services.shop_settings import ShopSettings
from app.services.ui import UI

router = Router(name="user.fallback")


@router.my_chat_member(F.chat.type == "private")
async def on_member_status(event: ChatMemberUpdated, session: AsyncSession) -> None:
    blocked = event.new_chat_member.status == "kicked"
    await users.set_flag(session, event.from_user.id, is_blocked_bot=blocked)
    await session.commit()


@router.message()
async def on_any_message(
    message: Message, session: AsyncSession, ui: UI, shop: ShopSettings, is_admin: bool = False
) -> None:
    await ui.drop(message)
    if is_admin:
        return
    user = await users.get(session, message.chat.id) or await users.upsert(session, message.from_user)  # type: ignore[arg-type]
    await session.commit()
    await show_home(message.chat.id, user, ui, await shop.get())


@router.callback_query()
async def on_stale_callback(cb: CallbackQuery) -> None:
    await cb.answer()
