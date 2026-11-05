"""Excel eksport. Fayl CPU'da yasaladi — event loop'ni to'xtatmaslik uchun alohida thread'da."""
from __future__ import annotations

import asyncio
import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import payments, users
from app.utils.timez import naive_local

STATUS_UZ = {"pending": "Kutilmoqda", "approved": "Tasdiqlangan", "rejected": "Rad etilgan"}


def _build(headers: list[str], rows: list[list[object]], title: str) -> bytes:
    wb = Workbook(write_only=False)
    ws = wb.active
    ws.title = title
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for r in rows:
        ws.append(r)
    for i, h in enumerate(headers, start=1):
        ws.column_dimensions[get_column_letter(i)].width = max(12, len(h) + 4)
    ws.freeze_panes = "A2"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def users_xlsx(session: AsyncSession) -> bytes:
    data = await users.all_users(session)
    rows = [
        [
            u.telegram_id, u.first_name, u.last_name or "", f"@{u.username}" if u.username else "",
            u.source or "", "Ha" if u.has_purchased else "Yo'q", "Ha" if u.is_banned else "Yo'q",
            "Ha" if u.is_blocked_bot else "Yo'q", naive_local(u.created_at), naive_local(u.last_active_at),
        ]
        for u in data
    ]
    headers = ["ID", "Ism", "Familiya", "Username", "Manba", "Xarid qilgan", "Bloklangan",
               "Botni bloklagan", "Ro'yxatdan o'tgan", "Oxirgi faollik"]
    return await asyncio.to_thread(_build, headers, rows, "Userlar")


async def payments_xlsx(session: AsyncSession, since: datetime | None) -> bytes:
    data = await payments.export_rows(session, since)
    rows = [
        [
            p.id, u.telegram_id, u.full_name, f"@{u.username}" if u.username else "", p.amount,
            STATUS_UZ.get(p.status.value, p.status.value), p.reviewed_by or "", p.reject_reason or "",
            naive_local(p.created_at), naive_local(p.reviewed_at),
        ]
        for p, u in data
    ]
    headers = ["To'lov ID", "User ID", "Ism", "Username", "Summa", "Holat", "Admin ID", "Rad sababi",
               "Yaratilgan", "Ko'rib chiqilgan"]
    return await asyncio.to_thread(_build, headers, rows, "Sotuvlar")
