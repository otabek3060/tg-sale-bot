from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("Asia/Tashkent")


def set_timezone(name: str) -> None:
    global _TZ
    _TZ = ZoneInfo(name)


def tz() -> ZoneInfo:
    return _TZ


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def periods() -> tuple[datetime, datetime, datetime]:
    """Mahalliy vaqt bo'yicha: bugun 00:00, 7 kun oldin, 30 kun oldin (UTC'da)."""
    local_now = datetime.now(_TZ)
    day = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        day.astimezone(timezone.utc),
        (day - timedelta(days=6)).astimezone(timezone.utc),
        (day - timedelta(days=29)).astimezone(timezone.utc),
    )


def fmt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.astimezone(_TZ).strftime("%d.%m.%Y %H:%M")


def naive_local(dt: datetime | None) -> datetime | None:
    """Excel timezone'li sanalarni qo'llamaydi."""
    return dt.astimezone(_TZ).replace(tzinfo=None) if dt else None
