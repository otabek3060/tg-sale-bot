"""/admin, pastki menyu tugmalari va bosh ekran."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app import keyboards as kb
from app.callbacks import AdmCb
from app.handlers.admin import broadcast, sales, settings, users
from app.handlers.admin.common import IsAdmin, dashboard
from app.services.access import Access
from app.services.broadcast import Broadcaster
from app.services.shop_settings import ShopSettings
from app.services.ui import UI
from app.texts import uz
from app.utils.tg import quiet

router = Router(name="admin.panel")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

KB_MSG = "ui:kb:{}"  # pastki klaviatura biriktirilgan xabar ID si


async def _replace_kb_message(message: Message, redis: Redis, text: str, markup: object) -> None:
    key = KB_MSG.format(message.chat.id)
    old = await redis.get(key)
    if old:
        await quiet(message.bot.delete_message(message.chat.id, int(old)))  # type: ignore[union-attr]
    m = await message.answer(text, reply_markup=markup)  # type: ignore[arg-type]
    await redis.set(key, m.message_id, ex=48 * 3600)


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext, session: AsyncSession, ui: UI, redis: Redis) -> None:
    await state.clear()
    await ui.drop(message)
    await _replace_kb_message(message, redis, "🛠 Admin panel ochildi.", kb.admin_reply())
    await dashboard(message.chat.id, session, ui, new=True)


@router.message(F.text == uz.BTN_EXIT)
async def on_exit(message: Message, state: FSMContext, ui: UI, redis: Redis) -> None:
    await state.clear()
    await ui.drop(message)
    await _replace_kb_message(message, redis, "🏠 Admin paneldan chiqildi. Qayta kirish: /admin", ReplyKeyboardRemove())
    await ui.persist(message.chat.id)


@router.message(F.text == uz.BTN_SETTINGS)
async def on_settings(message: Message, state: FSMContext, ui: UI, shop: ShopSettings, access: Access) -> None:
    await state.clear()
    await ui.drop(message)
    await settings.show(message.chat.id, ui, shop, access, new=True)


@router.message(F.text == uz.BTN_USERS)
async def on_users(message: Message, state: FSMContext, session: AsyncSession, ui: UI) -> None:
    await state.clear()
    await ui.drop(message)
    await users.show(message.chat.id, session, ui, new=True)


@router.message(F.text == uz.BTN_SALES)
async def on_sales(message: Message, state: FSMContext, session: AsyncSession, ui: UI) -> None:
    await state.clear()
    await ui.drop(message)
    await sales.show(message.chat.id, session, ui, new=True)


@router.message(F.text == uz.BTN_BROADCAST)
async def on_broadcast(message: Message, state: FSMContext, ui: UI, broadcaster: Broadcaster) -> None:
    await state.clear()
    await ui.drop(message)
    await broadcast.start(message.chat.id, state, ui, broadcaster)


@router.callback_query(AdmCb.filter(F.s == "home"))
async def on_home(cb: CallbackQuery, state: FSMContext, session: AsyncSession, ui: UI) -> None:
    await state.clear()
    await dashboard(cb.from_user.id, session, ui)
    await cb.answer()
