from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import users
from app.handlers.user.common import show_home
from app.services.shop_settings import ShopSettings
from app.services.ui import UI

router = Router(name="user.start")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    state: FSMContext,
    ui: UI,
    shop: ShopSettings,
) -> None:
    await state.clear()
    # ID, ism, familiya, username avtomatik saqlanadi (UPSERT — dublikat bo'lmaydi)
    user = await users.upsert(session, message.from_user, source=command.args)  # type: ignore[arg-type]
    await session.commit()  # DB ishi tugadi — ulanish pulga qaytdi, endi Telegram chaqiruvlari
    s = await shop.get()
    await ui.drop(message)
    await show_home(message.chat.id, user, ui, s, new=True)
