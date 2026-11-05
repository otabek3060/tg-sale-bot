from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app import keyboards as kb
from app.callbacks import UserCb
from app.db.repositories import payments, users
from app.handlers.user.common import payment_screen, show_home
from app.services.payments import LinkError, PaymentService
from app.services.shop_settings import ShopSettings
from app.services.ui import UI
from app.states import BuyStates
from app.texts import uz

router = Router(name="user.buy")
log = logging.getLogger(__name__)


@router.callback_query(UserCb.filter(F.action.in_({"buy", "retry"})))
async def on_buy(
    cb: CallbackQuery, session: AsyncSession, state: FSMContext, ui: UI, shop: ShopSettings
) -> None:
    s = await shop.get()
    if not s.sales_enabled:
        await cb.answer(uz.SALES_OFF, show_alert=True)
        return
    pending = await payments.has_pending(session, cb.from_user.id)
    await session.commit()
    if pending:
        await cb.answer(uz.PENDING_EXISTS, show_alert=True)
        return
    await state.set_state(BuyStates.waiting_receipt)
    await ui.render(cb.from_user.id, payment_screen(s), kb.payment_details())
    await cb.answer()


@router.callback_query(UserCb.filter(F.action == "back"))
async def on_back(
    cb: CallbackQuery, session: AsyncSession, state: FSMContext, ui: UI, shop: ShopSettings
) -> None:
    await state.clear()
    user = await users.get(session, cb.from_user.id) or await users.upsert(session, cb.from_user)
    await session.commit()
    await show_home(cb.from_user.id, user, ui, await shop.get())
    await cb.answer()


@router.callback_query(UserCb.filter(F.action == "link"))
async def on_get_link(
    cb: CallbackQuery, session: AsyncSession, redis: Redis, ui: UI, payment_service: PaymentService
) -> None:
    uid = cb.from_user.id
    user = await users.get(session, uid)
    await session.commit()
    if user is None or not user.has_purchased:
        await cb.answer(uz.NOT_PURCHASED, show_alert=True)
        return
    cooldown = f"linkcd:{uid}"
    if not await redis.set(cooldown, "1", nx=True, ex=600):
        await cb.answer(uz.LINK_COOLDOWN, show_alert=True)
        return
    try:
        link = await payment_service.link_for_user(uid)
    except LinkError:
        log.exception("link resend failed for %s", uid)
        await redis.delete(cooldown)
        await cb.answer(uz.TECH_ERROR, show_alert=True)
        return
    if link is None:
        await cb.answer(uz.NOT_PURCHASED, show_alert=True)
        return
    await ui.notify(uid, uz.link_again(link.url, link.hours))
    await cb.answer()
