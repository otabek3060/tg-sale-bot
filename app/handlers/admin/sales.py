"""💰 Sotuvlar: daromad, holatlar, adminlar statistikasi, kutilayotganlar, Excel."""
from __future__ import annotations

from datetime import timedelta
from html import escape

from aiogram import Bot, F, Router
from aiogram.types import BufferedInputFile, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from app import keyboards as kb
from app.callbacks import AdmCb
from app.db.repositories import misc, payments
from app.handlers.admin.common import IsAdmin
from app.services import export
from app.services.notifier import Notifier
from app.services.ui import UI
from app.texts import uz
from app.utils.timez import now_utc, periods, tz

router = Router(name="admin.sales")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


async def show(chat_id: int, session: AsyncSession, ui: UI, *, new: bool = False) -> None:
    st = await payments.sales_stats(session, *periods())
    per_admin = await payments.admin_stats(session)
    names = {a.telegram_id: a.name for a in await misc.admins(session)}
    await session.commit()

    def line(title: str, key: str) -> str:
        cnt, total = st[key]
        return f"{title}: <b>{cnt} ta · {uz.money(total)}</b>"

    text = "\n".join([
        "💰 <b>Sotuvlar</b>\n",
        line("📅 Bugun", "day"),
        line("🗓 7 kun", "week"),
        line("📆 30 kun", "month"),
        line("💼 Jami", "total"),
        "",
        f"⏳ Kutilmoqda: <b>{st['pending']}</b>",
        f"✅ Tasdiqlangan: <b>{st['approved']}</b>",
        f"❌ Rad etilgan: <b>{st['rejected']}</b>",
    ])
    if per_admin:
        text += "\n\n👮 <b>Adminlar bo'yicha:</b>\n" + "\n".join(
            f"• {escape(names.get(a) or str(a))} — ✅ {ok} · ❌ {no} · ⌛ {avg:.0f} daq"
            for a, ok, no, avg in per_admin
        )
    markup = kb.rows(
        [(f"⏳ Kutilayotganlar ({st['pending']})", AdmCb(s="sales", a="pending"))],
        [("📥 Excel", AdmCb(s="sales", a="xlsx"))],
        [("⬅️ Orqaga", AdmCb(s="home"))],
    )
    await ui.render(chat_id, text, markup, new=new)


@router.callback_query(AdmCb.filter(F.s == "sales"))
async def on_sales(
    cb: CallbackQuery, callback_data: AdmCb, session: AsyncSession, ui: UI, notifier: Notifier, bot: Bot
) -> None:
    chat_id, action = cb.from_user.id, callback_data.a
    if action == "pending":
        items = await payments.list_pending(session, limit=20)
        total = await payments.count_pending(session)
        await session.commit()
        if not items:
            await ui.render(chat_id, "✅ Kutilayotgan to'lov yo'q.", kb.back("sales"), new=True)
            await cb.answer()
            return
        buttons = [
            [(f"#{p.id} · {u.full_name[:20]} · {p.created_at.astimezone(tz()):%d.%m %H:%M}",
              AdmCb(s="sales", a="open", v=str(p.id)))]
            for p, u in items
        ]
        buttons.append([("⬅️ Orqaga", AdmCb(s="sales"))])
        text = f"⏳ <b>Kutilayotgan to'lovlar: {total}</b>\nEng eskisi birinchi. Chekni ochish uchun bosing."
        await ui.render(chat_id, text, kb.rows(*buttons), new=True)
    elif action == "open":
        if not await notifier.send_receipt_to(chat_id, int(callback_data.v)):
            await cb.answer("To'lov topilmadi", show_alert=True)
            return
    elif action == "xlsx":
        await ui.render(
            chat_id,
            "📥 Qaysi davr uchun eksport qilamiz?",
            kb.rows(
                [("Bugun", AdmCb(s="sales", a="x", v="1")), ("7 kun", AdmCb(s="sales", a="x", v="7"))],
                [("30 kun", AdmCb(s="sales", a="x", v="30")), ("Hammasi", AdmCb(s="sales", a="x", v="0"))],
                [("⬅️ Orqaga", AdmCb(s="sales"))],
            ),
        )
    elif action == "x":
        await cb.answer("⏳ Fayl tayyorlanmoqda...")
        days = int(callback_data.v or 0)
        since = None
        if days:
            day_start, _, _ = periods()
            since = day_start - timedelta(days=days - 1)
        data = await export.payments_xlsx(session, since)
        await session.commit()
        name = f"sales_{now_utc():%Y%m%d_%H%M}.xlsx"
        await bot.send_document(chat_id, BufferedInputFile(data, filename=name), caption="💰 Sotuvlar")
        return
    else:
        await show(chat_id, session, ui)
    await cb.answer()
