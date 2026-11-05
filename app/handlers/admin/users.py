"""👥 Userlar: statistika, qidirish, ro'yxat, kartochka, bloklash, xabar yozish, eksport."""
from __future__ import annotations

import math
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app import keyboards as kb
from app.callbacks import AdmCb
from app.db.repositories import misc, payments
from app.db.repositories import users as repo
from app.handlers.admin.common import IsAdmin
from app.services import export
from app.services.access import Access
from app.services.payments import LinkError, PaymentService
from app.services.ui import UI
from app.states import AdminStates
from app.texts import uz
from app.utils.tg import quiet
from app.utils.timez import fmt, now_utc, periods

router = Router(name="admin.users")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

PAGE = 10
STATUS_ICON = {"pending": "⏳", "approved": "✅", "rejected": "❌"}


async def show(chat_id: int, session: AsyncSession, ui: UI, *, new: bool = False) -> None:
    st = await repo.stats(session, *periods())
    await session.commit()
    conv = (st["buyers"] / st["total"] * 100) if st["total"] else 0
    text = (
        "👥 <b>Userlar</b>\n\n"
        f"Jami: <b>{st['total']}</b>\n"
        f"Bugun: <b>{st['day']}</b> · 7 kun: <b>{st['week']}</b> · 30 kun: <b>{st['month']}</b>\n\n"
        f"🛒 Xarid qilganlar: <b>{st['buyers']}</b> (konversiya {conv:.1f}%)\n"
        f"🚫 Botni bloklaganlar: <b>{st['blocked']}</b>\n"
        f"⛔️ Bloklanganlar: <b>{st['banned']}</b>"
    )
    markup = kb.rows(
        [("🔍 Qidirish", AdmCb(s="users", a="search")), ("📄 Ro'yxat", AdmCb(s="users", a="list", v="0"))],
        [("📥 Excel", AdmCb(s="users", a="xlsx"))],
        [("⬅️ Orqaga", AdmCb(s="home"))],
    )
    await ui.render(chat_id, text, markup, new=new)


async def show_card(chat_id: int, user_id: int, session: AsyncSession, ui: UI, note: str = "") -> bool:
    u = await repo.get(session, user_id)
    if u is None:
        await session.commit()
        return False
    history = await payments.for_user(session, user_id)
    await session.commit()
    uname = f"@{escape(u.username)}" if u.username else "—"
    lines = [
        f"👤 <b>{escape(u.full_name)}</b>",
        f"🆔 <code>{u.telegram_id}</code> · {uname}",
        f"📅 Ro'yxatdan o'tgan: {fmt(u.created_at)}",
        f"🕒 Oxirgi faollik: {fmt(u.last_active_at)}",
        f"📣 Manba: {escape(u.source or '—')}",
        f"🛒 Xarid: {'✅ Ha' if u.has_purchased else 'Yo‘q'}",
    ]
    if u.is_banned:
        lines.append("⛔️ <b>Bloklangan</b>")
    if u.is_blocked_bot:
        lines.append("🚫 Botni bloklagan")
    if history:
        lines.append("\n<b>To'lovlar:</b>")
        for p in history:
            lines.append(f"{STATUS_ICON[p.status.value]} #{p.id} · {uz.money(p.amount)} · {fmt(p.created_at)}")
    if note:
        lines.append(f"\n{note}")
    uid = str(u.telegram_id)
    buttons = [
        [("✅ Blokdan chiqarish", AdmCb(s="user", a="unban", v=uid)) if u.is_banned
         else ("⛔️ Bloklash", AdmCb(s="user", a="ban", v=uid))],
        [("✉️ Xabar yozish", AdmCb(s="user", a="msg", v=uid))],
    ]
    if u.has_purchased:
        buttons.insert(1, [("🔗 Havolani qayta yuborish", AdmCb(s="user", a="link", v=uid))])
    buttons.append([("⬅️ Orqaga", AdmCb(s="users"))])
    await ui.render(chat_id, "\n".join(lines), kb.rows(*buttons))
    return True


@router.callback_query(AdmCb.filter(F.s == "users"))
async def on_users(
    cb: CallbackQuery, callback_data: AdmCb, state: FSMContext, session: AsyncSession, ui: UI, bot: Bot
) -> None:
    chat_id = cb.from_user.id
    await state.clear()
    if callback_data.a == "search":
        await state.set_state(AdminStates.search_user)
        await ui.render(chat_id, "🔍 User ID yoki @username yuboring:", kb.cancel("users"))
    elif callback_data.a == "list":
        page = max(0, int(callback_data.v or 0))
        total = await repo.count(session)
        pages = max(1, math.ceil(total / PAGE))
        page = min(page, pages - 1)
        items = await repo.page(session, page * PAGE, PAGE)
        await session.commit()
        buttons = [
            [(f"{'✅ ' if u.has_purchased else ''}{u.full_name[:28]} · {u.telegram_id}",
              AdmCb(s="user", v=str(u.telegram_id)))]
            for u in items
        ]
        nav = []
        if page > 0:
            nav.append(("◀️", AdmCb(s="users", a="list", v=str(page - 1))))
        nav.append((f"{page + 1}/{pages}", AdmCb(s="users", a="list", v=str(page))))
        if page < pages - 1:
            nav.append(("▶️", AdmCb(s="users", a="list", v=str(page + 1))))
        buttons += [nav, [("⬅️ Orqaga", AdmCb(s="users"))]]
        await ui.render(chat_id, f"📄 <b>Userlar ro'yxati</b> (jami {total})", kb.rows(*buttons))
    elif callback_data.a == "xlsx":
        await cb.answer("⏳ Fayl tayyorlanmoqda...")
        data = await export.users_xlsx(session)
        await session.commit()
        name = f"users_{now_utc():%Y%m%d_%H%M}.xlsx"
        await bot.send_document(chat_id, BufferedInputFile(data, filename=name), caption="👥 Userlar ro'yxati")
        return
    else:
        await show(chat_id, session, ui)
    await cb.answer()


@router.message(AdminStates.search_user)
async def on_search(message: Message, state: FSMContext, session: AsyncSession, ui: UI) -> None:
    await ui.drop(message)
    u = await repo.find(session, message.text or "")
    if u is None:
        await session.commit()
        await ui.render(message.chat.id, "🔍 Topilmadi. Boshqa ID yoki @username yuboring:", kb.cancel("users"))
        return
    await state.clear()
    await show_card(message.chat.id, u.telegram_id, session, ui)


@router.callback_query(AdmCb.filter(F.s == "user"))
async def on_user_action(
    cb: CallbackQuery,
    callback_data: AdmCb,
    state: FSMContext,
    session: AsyncSession,
    ui: UI,
    access: Access,
    payment_service: PaymentService,
) -> None:
    chat_id, uid, action = cb.from_user.id, int(callback_data.v), callback_data.a
    note = ""
    if action in ("ban", "unban"):
        if await access.is_admin(uid):
            await cb.answer("Adminni bloklab bo'lmaydi.", show_alert=True)
            return
        banned = action == "ban"
        await repo.set_flag(session, uid, is_banned=banned)
        await misc.audit(session, chat_id, action, user=uid)
        await session.commit()
        await access.set_banned(uid, banned)
        note = "⛔️ Bloklandi" if banned else "✅ Blokdan chiqarildi"
        if cb.message and cb.message.message_id != await _screen_id(ui, chat_id):
            # chek xabaridagi "🚫 Bloklash" tugmasi — kartochka ochmaymiz, tugmani olib tashlaymiz
            await quiet(cb.message.edit_reply_markup(reply_markup=None))
            await cb.answer(note, show_alert=True)
            return
    elif action == "link":
        try:
            link = await payment_service.link_for_user(uid)
        except LinkError as e:
            await cb.answer(f"⚠️ {e}", show_alert=True)
            return
        if link is None or not await ui.notify(uid, uz.link_again(link.url, link.hours)):
            await cb.answer("Yuborib bo'lmadi (xarid yo'q yoki user botni bloklagan).", show_alert=True)
            return
        note = "🔗 Havola yuborildi"
    elif action == "msg":
        await state.set_state(AdminStates.message_user)
        await state.update_data(uid=uid)
        await ui.render(chat_id, "✉️ Foydalanuvchiga yuboriladigan xabarni yozing (matn, rasm, fayl):",
                        kb.cancel("user", "", str(uid)))
        await cb.answer()
        return
    else:
        await state.clear()
    if not await show_card(chat_id, uid, session, ui, note):
        await cb.answer("User topilmadi", show_alert=True)
        return
    await cb.answer()


async def _screen_id(ui: UI, chat_id: int) -> int | None:
    raw = await ui.redis.hget(ui._key(chat_id), "id")
    return int(raw) if raw else None


@router.message(AdminStates.message_user)
async def on_message_user(message: Message, state: FSMContext, session: AsyncSession, ui: UI, bot: Bot) -> None:
    uid = int((await state.get_data()).get("uid", 0))
    await state.clear()
    try:
        await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=message.message_id)
        note = "✅ Xabar yuborildi"
    except TelegramForbiddenError:
        note = "🚫 Foydalanuvchi botni bloklagan"
    except TelegramBadRequest as e:
        note = f"⚠️ Yuborilmadi: {escape(e.message)}"
    await ui.drop(message)
    await show_card(message.chat.id, uid, session, ui, note)
