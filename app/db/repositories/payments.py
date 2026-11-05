from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminMessage, Payment, PaymentStatus, User


async def has_pending(session: AsyncSession, user_id: int) -> bool:
    res = await session.execute(
        select(Payment.id).where(Payment.user_id == user_id, Payment.status == PaymentStatus.pending).limit(1)
    )
    return res.scalar_one_or_none() is not None


async def find_duplicate(session: AsyncSession, file_unique_id: str) -> int | None:
    res = await session.execute(
        select(Payment.id).where(Payment.file_unique_id == file_unique_id).order_by(Payment.id).limit(1)
    )
    return res.scalar_one_or_none()


async def create(
    session: AsyncSession,
    *,
    user_id: int,
    amount: int,
    file_id: str,
    file_unique_id: str,
    file_type: str,
) -> Payment | None:
    """Yangi pending to'lov. Agar userda pending allaqachon bo'lsa (unique index) — None."""
    values = {
        "user_id": user_id,
        "amount": amount,
        "file_id": file_id,
        "file_unique_id": file_unique_id,
        "file_type": file_type,
        "duplicate_of": await find_duplicate(session, file_unique_id),
    }
    try:
        row = (await session.execute(_INSERT_PAYMENT, values)).one()
    except IntegrityError:
        await session.rollback()
        return None
    return Payment(**row._mapping)


_INSERT_PAYMENT = insert(Payment).returning(*Payment.__table__.c)


async def get_with_user(session: AsyncSession, payment_id: int) -> tuple[Payment, User] | None:
    res = await session.execute(
        select(Payment, User).join(User, User.telegram_id == Payment.user_id).where(Payment.id == payment_id)
    )
    row = res.one_or_none()
    return (row[0], row[1]) if row else None


async def decide(
    session: AsyncSession,
    payment_id: int,
    status: PaymentStatus,
    admin_id: int,
    reason: str | None = None,
) -> int | None:
    """Atomik o'tish pending -> approved/rejected. Faqat birinchi admin muvaffaqiyatli bo'ladi.
    Qaytaradi: user_id yoki None (allaqachon ko'rib chiqilgan)."""
    res = await session.execute(
        update(Payment)
        .where(Payment.id == payment_id, Payment.status == PaymentStatus.pending)
        .values(status=status, reviewed_by=admin_id, reviewed_at=func.now(), reject_reason=reason)
        .returning(Payment.user_id)
    )
    return res.scalar_one_or_none()


async def is_pending(session: AsyncSession, payment_id: int) -> bool:
    res = await session.execute(select(Payment.status).where(Payment.id == payment_id))
    return res.scalar_one_or_none() == PaymentStatus.pending


async def set_link(session: AsyncSession, payment_id: int, link: str) -> None:
    await session.execute(update(Payment).where(Payment.id == payment_id).values(invite_link=link))


async def last_approved(session: AsyncSession, user_id: int) -> Payment | None:
    res = await session.execute(
        select(Payment)
        .where(Payment.user_id == user_id, Payment.status == PaymentStatus.approved)
        .order_by(Payment.id.desc())
        .limit(1)
    )
    return res.scalar_one_or_none()


async def for_user(session: AsyncSession, user_id: int, limit: int = 5) -> list[Payment]:
    res = await session.execute(
        select(Payment).where(Payment.user_id == user_id).order_by(Payment.id.desc()).limit(limit)
    )
    return list(res.scalars())


async def list_pending(session: AsyncSession, limit: int = 20) -> list[tuple[Payment, User]]:
    res = await session.execute(
        select(Payment, User)
        .join(User, User.telegram_id == Payment.user_id)
        .where(Payment.status == PaymentStatus.pending)
        .order_by(Payment.created_at)
        .limit(limit)
    )
    return [(p, u) for p, u in res.all()]


async def count_pending(session: AsyncSession) -> int:
    res = await session.execute(
        select(func.count()).select_from(Payment).where(Payment.status == PaymentStatus.pending)
    )
    return res.scalar_one()


async def overdue_unreminded(session: AsyncSession, minutes: int) -> list[int]:
    border = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    res = await session.execute(
        select(Payment.id).where(
            Payment.status == PaymentStatus.pending,
            Payment.created_at < border,
            Payment.reminded_at.is_(None),
        )
    )
    return list(res.scalars())


async def mark_reminded(session: AsyncSession, ids: list[int]) -> None:
    await session.execute(update(Payment).where(Payment.id.in_(ids)).values(reminded_at=func.now()))


# --- admin_messages ---------------------------------------------------------------

_ins = pg_insert(AdminMessage)
# Statement bir marta quriladi va SQLAlchemy keshida qoladi; qatorlar executemany bilan beriladi.
# (.values([...]) har safar yangi SQL kompilyatsiya qilardi — yuklama ostida ~2.5 ms CPU)
_UPSERT_ADMIN_MSG = _ins.on_conflict_do_update(
    index_elements=[AdminMessage.payment_id, AdminMessage.admin_id],
    set_={"message_id": _ins.excluded.message_id},
)


async def save_admin_messages(session: AsyncSession, payment_id: int, rows: list[tuple[int, int]]) -> None:
    if not rows:
        return
    await session.execute(
        _UPSERT_ADMIN_MSG, [{"payment_id": payment_id, "admin_id": a, "message_id": m} for a, m in rows]
    )


async def admin_messages(session: AsyncSession, payment_id: int) -> list[tuple[int, int]]:
    res = await session.execute(
        select(AdminMessage.admin_id, AdminMessage.message_id).where(AdminMessage.payment_id == payment_id)
    )
    return [(a, m) for a, m in res.all()]


# --- statistika va eksport --------------------------------------------------------

async def sales_stats(session: AsyncSession, day: datetime, week: datetime, month: datetime) -> dict:
    approved = Payment.status == PaymentStatus.approved
    stmt = select(
        func.count().filter(approved, Payment.reviewed_at >= day),
        func.coalesce(func.sum(Payment.amount).filter(approved, Payment.reviewed_at >= day), 0),
        func.count().filter(approved, Payment.reviewed_at >= week),
        func.coalesce(func.sum(Payment.amount).filter(approved, Payment.reviewed_at >= week), 0),
        func.count().filter(approved, Payment.reviewed_at >= month),
        func.coalesce(func.sum(Payment.amount).filter(approved, Payment.reviewed_at >= month), 0),
        func.count().filter(approved),
        func.coalesce(func.sum(Payment.amount).filter(approved), 0),
        func.count().filter(Payment.status == PaymentStatus.pending),
        func.count().filter(Payment.status == PaymentStatus.rejected),
    ).select_from(Payment)
    r = (await session.execute(stmt)).one()
    return {
        "day": (r[0], r[1]), "week": (r[2], r[3]), "month": (r[4], r[5]), "total": (r[6], r[7]),
        "pending": r[8], "approved": r[6], "rejected": r[9],
    }


async def admin_stats(session: AsyncSession) -> list[tuple[int, int, int, float]]:
    """(admin_id, tasdiqlagan, rad etgan, o'rtacha ko'rib chiqish daqiqada)"""
    stmt = (
        select(
            Payment.reviewed_by,
            func.count().filter(Payment.status == PaymentStatus.approved),
            func.count().filter(Payment.status == PaymentStatus.rejected),
            func.avg(func.extract("epoch", Payment.reviewed_at - Payment.created_at)) / 60,
        )
        .where(Payment.reviewed_by.is_not(None))
        .group_by(Payment.reviewed_by)
        .order_by(func.count().desc())
    )
    return [(a, ok, no, float(avg or 0)) for a, ok, no, avg in (await session.execute(stmt)).all()]


async def export_rows(session: AsyncSession, since: datetime | None) -> list[tuple[Payment, User]]:
    stmt = select(Payment, User).join(User, User.telegram_id == Payment.user_id).order_by(Payment.id)
    if since is not None:
        stmt = stmt.where(Payment.created_at >= since)
    return [(p, u) for p, u in (await session.execute(stmt)).all()]
