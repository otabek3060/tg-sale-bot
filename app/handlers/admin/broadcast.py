"""📢 Ommaviy xabar yuborish."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app import keyboards as kb
from app.callbacks import AdmCb
from app.config import Config
from app.db.repositories import users
from app.handlers.admin.common import IsAdmin, dashboard
from app.services.broadcast import Broadcaster
from app.services.ui import UI
from app.states import AdminStates

router = Router(name="admin.broadcast")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

AUDIENCES = {"all": "Hammaga", "buyers": "Xaridorlarga", "nonbuyers": "Xarid qilmaganlarga"}


async def start(chat_id: int, state: FSMContext, ui: UI, broadcaster: Broadcaster) -> None:
    if await broadcaster.is_running():
        await ui.render(chat_id, "⏳ Hozir boshqa xabar yuborilmoqda. Tugashini kuting.", kb.back(), new=True)
        return
    await state.set_state(AdminStates.broadcast_content)
    await ui.render(
        chat_id,
        "📢 Foydalanuvchilarga yubormoqchi bo'lgan xabarni yuboring (matn, rasm, video, fayl — har qanday).",
        kb.cancel("bc"),
        new=True,
    )


@router.message(AdminStates.broadcast_content)
async def on_content(message: Message, state: FSMContext, session: AsyncSession, ui: UI) -> None:
    # Xabarni o'chirmaymiz: copy_message manba xabar mavjud bo'lishini talab qiladi
    counts = {a: await users.audience_count(session, a) for a in AUDIENCES}
    await session.commit()
    await state.set_state(AdminStates.broadcast_confirm)
    await state.update_data(from_chat=message.chat.id, mid=message.message_id)
    await ui.render(
        message.chat.id,
        "👆 Shu xabar yuboriladi. Kimga?",
        kb.rows(
            *[[(f"{title} ({counts[a]})", AdmCb(s="bc", a="aud", v=a))] for a, title in AUDIENCES.items()],
            [("❌ Bekor qilish", AdmCb(s="bc"))],
        ),
        new=True,
    )


@router.callback_query(AdmCb.filter(F.s == "bc"), AdminStates.broadcast_confirm)
async def on_confirm(
    cb: CallbackQuery,
    callback_data: AdmCb,
    state: FSMContext,
    session: AsyncSession,
    ui: UI,
    broadcaster: Broadcaster,
    config: Config,
) -> None:
    chat_id = cb.from_user.id
    if callback_data.a == "aud" and callback_data.v in AUDIENCES:
        n = await users.audience_count(session, callback_data.v)
        await session.commit()
        minutes = max(1, round(n / config.broadcast_rate / 60))
        await ui.render(
            chat_id,
            f"📢 <b>{n}</b> ta foydalanuvchiga ({AUDIENCES[callback_data.v].lower()}) yuboriladi.\n"
            f"Taxminiy vaqt: ~{minutes} daqiqa.\n\nTasdiqlaysizmi?",
            kb.rows(
                [("✅ Yuborish", AdmCb(s="bc", a="go", v=callback_data.v))],
                [("❌ Bekor qilish", AdmCb(s="bc"))],
            ),
        )
    elif callback_data.a == "go" and callback_data.v in AUDIENCES:
        data = await state.get_data()
        await state.clear()
        started = await broadcaster.start(chat_id, int(data["from_chat"]), int(data["mid"]), callback_data.v)
        text = (
            "🚀 Yuborish boshlandi. Tugagach hisobot keladi."
            if started else "⏳ Hozir boshqa xabar yuborilmoqda."
        )
        await ui.render(chat_id, text, kb.back())
    else:
        await state.clear()
        await dashboard(chat_id, session, ui)
    await cb.answer()


@router.callback_query(AdmCb.filter(F.s == "bc"))
async def on_cancel(cb: CallbackQuery, state: FSMContext, session: AsyncSession, ui: UI) -> None:
    await state.clear()
    await dashboard(cb.from_user.id, session, ui)
    await cb.answer()
