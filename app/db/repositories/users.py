from __future__ import annotations

from datetime import datetime

from aiogram.types import User as TgUser
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


_ins = pg_insert(User)
# Statement bir marta quriladi (SQLAlchemy kompilyatsiya keshi), ORM entity yuklash o'rniga Core RETURNING —
# eng ko'p chaqiriladigan so'rov uchun CPU ~2 barobar kam.
_UPSERT = _ins.on_conflict_do_update(
    index_elements=[User.telegram_id],
    set_={
        "first_name": _ins.excluded.first_name,
        "last_name": _ins.excluded.last_name,
        "username": _ins.excluded.username,
        "language_code": _ins.excluded.language_code,
        "last_active_at": func.now(),
        "is_blocked_bot": False,
    },
).returning(*User.__table__.c)


async def upsert(session: AsyncSession, tg: TgUser, source: str | None = None) -> User:
    """Bitta so'rov: yangi bo'lsa qo'shadi, bor bo'lsa ism/username/faollikni yangilaydi.
    `source` faqat birinchi marta yoziladi (reklama manbasi o'zgarmasligi uchun).
    Qaytadigan User — sessiyaga bog'lanmagan oddiy ma'lumot obyekti."""
    row = (
        await session.execute(
            _UPSERT,
            {
                "telegram_id": tg.id,
                "first_name": (tg.first_name or "")[:128],
                "last_name": tg.last_name[:128] if tg.last_name else None,
                "username": tg.username[:64] if tg.username else None,
                "language_code": tg.language_code[:8] if tg.language_code else None,
                "source": source[:64] if source else None,
            },
        )
    ).one()
    return User(**row._mapping)


async def get(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def find(session: AsyncSession, query: str) -> User | None:
    q = query.strip().lstrip("@")
    if q.lstrip("-").isdigit():
        return await session.get(User, int(q))
    res = await session.execute(select(User).where(func.lower(User.username) == q.lower()).limit(1))
    return res.scalar_one_or_none()


async def page(session: AsyncSession, offset: int, limit: int) -> list[User]:
    res = await session.execute(
        select(User).order_by(User.created_at.desc(), User.telegram_id.desc()).offset(offset).limit(limit)
    )
    return list(res.scalars())


async def count(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(User))).scalar_one()


async def set_flag(session: AsyncSession, user_id: int, **values: bool) -> None:
    await session.execute(update(User).where(User.telegram_id == user_id).values(**values))


async def banned_ids(session: AsyncSession) -> list[int]:
    res = await session.execute(select(User.telegram_id).where(User.is_banned.is_(True)))
    return list(res.scalars())


async def audience_batch(session: AsyncSession, audience: str, after_id: int, limit: int = 1000) -> list[int]:
    """Broadcast uchun ID larni keyset-pagination bilan bo'lib-bo'lib beradi (OFFSET'siz, tez)."""
    stmt = (
        select(User.telegram_id)
        .where(User.telegram_id > after_id, User.is_banned.is_(False), User.is_blocked_bot.is_(False))
        .order_by(User.telegram_id)
        .limit(limit)
    )
    if audience == "buyers":
        stmt = stmt.where(User.has_purchased.is_(True))
    elif audience == "nonbuyers":
        stmt = stmt.where(User.has_purchased.is_(False))
    return list((await session.execute(stmt)).scalars())


async def mark_blocked(session: AsyncSession, ids: list[int]) -> None:
    if ids:
        await session.execute(update(User).where(User.telegram_id.in_(ids)).values(is_blocked_bot=True))


async def audience_count(session: AsyncSession, audience: str) -> int:
    stmt = select(func.count()).select_from(User).where(
        User.is_banned.is_(False), User.is_blocked_bot.is_(False)
    )
    if audience == "buyers":
        stmt = stmt.where(User.has_purchased.is_(True))
    elif audience == "nonbuyers":
        stmt = stmt.where(User.has_purchased.is_(False))
    return (await session.execute(stmt)).scalar_one()


async def all_users(session: AsyncSession) -> list[User]:
    res = await session.execute(select(User).order_by(User.created_at))
    return list(res.scalars())


async def stats(session: AsyncSession, day: datetime, week: datetime, month: datetime) -> dict[str, int]:
    stmt = select(
        func.count(),
        func.count().filter(User.created_at >= day),
        func.count().filter(User.created_at >= week),
        func.count().filter(User.created_at >= month),
        func.count().filter(User.has_purchased.is_(True)),
        func.count().filter(User.is_blocked_bot.is_(True)),
        func.count().filter(User.is_banned.is_(True)),
    ).select_from(User)
    total, d, w, m, buyers, blocked, banned = (await session.execute(stmt)).one()
    return {
        "total": total, "day": d, "week": w, "month": m,
        "buyers": buyers, "blocked": blocked, "banned": banned,
    }
