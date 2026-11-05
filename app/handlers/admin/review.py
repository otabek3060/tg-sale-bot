"""To'lovni tasdiqlash / rad etish."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app import keyboards as kb
from app.callbacks import AdmCb, PayCb
from app.db.models import PaymentStatus
from app.db.repositories import payments, users
from app.handlers.admin.common import IsAdmin
from app.services.notifier import Notifier, admin_label
from app.services.payments import LinkError, PaymentService
from app.services.ui import UI
from app.states import AdminStates
from app.texts import uz
from app.utils.tasks import BackgroundTasks
from app.utils.tg import quiet
from app.utils.timez import fmt, now_utc

router = Router(name="admin.review")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())
log = logging.getLogger(__name__)

ALREADY = "Bu to'lov allaqachon ko'rib chiqilgan."


async def _already(cb: CallbackQuery, session: AsyncSession, pid: int) -> None:
    row = await payments.get_with_user(session, pid)
    await session.commit()
    status = row[0].status if row else None
    who = {PaymentStatus.approved: "✅ tasdiqlangan", PaymentStatus.rejected: "❌ rad etilgan"}.get(status, "")
    await cb.answer(f"{ALREADY} {who}".strip(), show_alert=True)
    await quiet(cb.message.edit_reply_markup(reply_markup=None))  # type: ignore[union-attr]


@router.callback_query(PayCb.filter(F.action == "ok"))
async def on_approve(
    cb: CallbackQuery,
    callback_data: PayCb,
    session: AsyncSession,
    payment_service: PaymentService,
    ui: UI,
    notifier: Notifier,
    tasks: BackgroundTasks,
) -> None:
    pid = callback_data.pid
    try:
        result = await payment_service.approve(pid, cb.from_user.id)
    except LinkError as e:
        await cb.answer(f"⚠️ Havola yaratib bo'lmadi: {e}\nTo'lov kutilmoqda holatida qoldi.", show_alert=True)
        return
    if result is None:
        await _already(cb, session, pid)
        return
    user_id, link = result
    await cb.answer("✅ Tasdiqlandi, havola yuborildi")

    delivered = await ui.notify(user_id, uz.approved(link.url, link.hours))
    status = f"✅ <b>Tasdiqladi:</b> {admin_label(cb.from_user)} · {fmt(now_utc())}"
    if not delivered:
        await users.set_flag(session, user_id, is_blocked_bot=True)
        await session.commit()
        status += "\n⚠️ Foydalanuvchi botni bloklagan — havola yetkazilmadi."
    tasks.spawn(notifier.finalize(pid, status), name=f"finalize#{pid}")


@router.callback_query(PayCb.filter(F.action == "no"))
async def on_reject_menu(cb: CallbackQuery, callback_data: PayCb, session: AsyncSession) -> None:
    pending = await payments.get_with_user(session, callback_data.pid)
    await session.commit()
    if pending is None or pending[0].status != PaymentStatus.pending:
        await _already(cb, session, callback_data.pid)
        return
    await quiet(cb.message.edit_reply_markup(reply_markup=kb.reject_reasons(callback_data.pid)))  # type: ignore[union-attr]
    await cb.answer("Sababni tanlang")


@router.callback_query(PayCb.filter(F.action == "back"))
async def on_reject_cancel(cb: CallbackQuery, callback_data: PayCb, state: FSMContext) -> None:
    await state.clear()
    await quiet(cb.message.edit_reply_markup(reply_markup=kb.review(callback_data.pid)))  # type: ignore[union-attr]
    await cb.answer()


@router.callback_query(PayCb.filter(F.action == "custom"))
async def on_reject_custom(cb: CallbackQuery, callback_data: PayCb, state: FSMContext, ui: UI) -> None:
    await state.set_state(AdminStates.reject_reason)
    await state.update_data(pid=callback_data.pid)
    await ui.render(
        cb.from_user.id,
        f"✍️ To'lov <b>#{callback_data.pid}</b> uchun rad etish sababini yozing:",
        kb.rows([("❌ Bekor qilish", AdmCb(s="home"))]),
        new=True,
    )
    await cb.answer()


async def _do_reject(
    *,
    pid: int,
    reason: str,
    admin: object,
    admin_id: int,
    session: AsyncSession,
    payment_service: PaymentService,
    ui: UI,
    notifier: Notifier,
    tasks: BackgroundTasks,
    offer_ban: bool,
) -> bool:
    user_id = await payment_service.reject(pid, admin_id, reason)
    if user_id is None:
        return False
    delivered = await ui.notify(user_id, uz.rejected(reason), kb.retry())
    status = f"❌ <b>Rad etdi:</b> {admin_label(admin)} · {fmt(now_utc())}\nSabab: {reason}"
    if not delivered:
        await users.set_flag(session, user_id, is_blocked_bot=True)
        await session.commit()
        status += "\n⚠️ Foydalanuvchi botni bloklagan."
    extra = {admin_id: kb.ban_offer(user_id)} if offer_ban else None
    tasks.spawn(notifier.finalize(pid, status, extra), name=f"finalize#{pid}")
    return True


@router.callback_query(PayCb.filter(F.action == "r"))
async def on_reject_reason(
    cb: CallbackQuery,
    callback_data: PayCb,
    session: AsyncSession,
    payment_service: PaymentService,
    ui: UI,
    notifier: Notifier,
    tasks: BackgroundTasks,
) -> None:
    reason = uz.REJECT_REASONS.get(callback_data.code, "Boshqa")
    ok = await _do_reject(
        pid=callback_data.pid, reason=reason, admin=cb.from_user, admin_id=cb.from_user.id,
        session=session, payment_service=payment_service, ui=ui, notifier=notifier, tasks=tasks,
        offer_ban=callback_data.code == "fake",
    )
    if not ok:
        await _already(cb, session, callback_data.pid)
        return
    await cb.answer("❌ Rad etildi")


@router.message(AdminStates.reject_reason, F.text)
async def on_reject_reason_text(
    message: Message,
    state: FSMContext,
    session: AsyncSession,
    payment_service: PaymentService,
    ui: UI,
    notifier: Notifier,
    tasks: BackgroundTasks,
) -> None:
    pid = (await state.get_data()).get("pid")
    await state.clear()
    await ui.drop(message)
    if not pid:
        return
    ok = await _do_reject(
        pid=int(pid), reason=(message.text or "").strip()[:256], admin=message.from_user,
        admin_id=message.chat.id, session=session, payment_service=payment_service, ui=ui,
        notifier=notifier, tasks=tasks, offer_ban=False,
    )
    text = f"❌ To'lov #{pid} rad etildi." if ok else f"ℹ️ To'lov #{pid}: {ALREADY}"
    await ui.render(message.chat.id, text, kb.back())
