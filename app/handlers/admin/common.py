from __future__ import annotations

from typing import Any

from aiogram.filters import BaseFilter
from sqlalchemy.ext.asyncio import AsyncSession

from app import keyboards as kb
from app.callbacks import AdmCb
from app.db.repositories import payments, users
from app.services.ui import UI
from app.texts import uz
from app.utils.timez import periods


class IsAdmin(BaseFilter):
    """`is_admin` GuardMiddleware tomonidan hisoblanadi — qo'shimcha so'rov yo'q."""

    async def __call__(self, event: Any, is_admin: bool = False) -> bool:
        return is_admin


async def dashboard(chat_id: int, session: AsyncSession, ui: UI, *, new: bool = False) -> None:
    day, week, month = periods()
    sales = await payments.sales_stats(session, day, week, month)
    ustats = await users.stats(session, day, week, month)
    await session.commit()
    cnt, total = sales["day"]
    text = (
        "🛠 <b>Admin panel</b>\n\n"
        f"⏳ Kutilayotgan to'lovlar: <b>{sales['pending']}</b>\n"
        f"💰 Bugun: <b>{cnt} ta · {uz.money(total)}</b>\n"
        f"👥 Bugun yangi userlar: <b>{ustats['day']}</b> (jami {ustats['total']})\n\n"
        "Pastdagi menyudan bo'limni tanlang 👇"
    )
    markup = kb.rows([(f"⏳ Kutilayotganlar ({sales['pending']})", AdmCb(s="sales", a="pending"))])
    await ui.render(chat_id, text, markup, new=new)
