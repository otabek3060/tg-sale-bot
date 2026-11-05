"""Adminlar, sozlamalar va audit jurnali uchun repozitoriy."""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Admin, AuditLog, Setting


# --- admins -----------------------------------------------------------------------

async def admin_ids(session: AsyncSession) -> list[int]:
    return list((await session.execute(select(Admin.telegram_id))).scalars())


async def admins(session: AsyncSession) -> list[Admin]:
    return list((await session.execute(select(Admin).order_by(Admin.created_at))).scalars())


async def add_admin(
    session: AsyncSession, telegram_id: int, name: str | None, added_by: int | None, is_owner: bool = False
) -> None:
    stmt = pg_insert(Admin).values(telegram_id=telegram_id, name=name, added_by=added_by, is_owner=is_owner)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Admin.telegram_id],
        set_={"is_owner": stmt.excluded.is_owner, "name": func.coalesce(stmt.excluded.name, Admin.name)},
    )
    await session.execute(stmt)


async def remove_admin(session: AsyncSession, telegram_id: int) -> None:
    await session.execute(delete(Admin).where(Admin.telegram_id == telegram_id, Admin.is_owner.is_(False)))


# --- settings ---------------------------------------------------------------------

async def all_settings(session: AsyncSession) -> dict[str, str]:
    return {k: v for k, v in (await session.execute(select(Setting.key, Setting.value))).all()}


async def set_setting(session: AsyncSession, key: str, value: str, admin_id: int | None) -> None:
    stmt = pg_insert(Setting).values(key=key, value=value, updated_by=admin_id)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Setting.key],
        set_={"value": stmt.excluded.value, "updated_by": stmt.excluded.updated_by, "updated_at": func.now()},
    )
    await session.execute(stmt)


# --- audit ------------------------------------------------------------------------

async def audit(session: AsyncSession, admin_id: int, action: str, **payload: Any) -> None:
    session.add(AuditLog(admin_id=admin_id, action=action, payload=payload or None))
