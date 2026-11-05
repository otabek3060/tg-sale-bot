"""Do'kon sozlamalari: Postgres'da saqlanadi, Redis'da keshlanadi.
Har bir o'qish = 1 ta HGETALL (~0.2 ms). O'zgarganda kesh darhol o'chiriladi — barcha instansiyalar
keyingi so'rovdayoq yangi qiymatni ko'radi."""
from __future__ import annotations

import time
from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repositories import misc
from app.texts import uz

KEY = "cache:settings"
TTL = 600
LOCAL_TTL = 1.0  # jarayon ichidagi kesh: boshqa instansiyalarda o'zgarish ≤ 1 s da ko'rinadi

DEFAULTS: dict[str, str] = {
    "card_number": "8600000000000000",
    "card_holder": "ISM FAMILIYA",
    "price": "50000",
    "product_text": uz.DEFAULT_PRODUCT_TEXT,
    "product_photo": "",
    "link_mode": "static",       # static | invite
    "channel_id": "",
    "static_link": "",
    "sales_enabled": "1",
}


@dataclass(frozen=True, slots=True)
class Shop:
    card_number: str
    card_holder: str
    price: int
    product_text: str
    product_photo: str
    link_mode: str
    channel_id: str
    static_link: str
    sales_enabled: bool

    @classmethod
    def from_raw(cls, raw: dict[str, str]) -> Shop:
        d = {**DEFAULTS, **raw}
        return cls(
            card_number=d["card_number"],
            card_holder=d["card_holder"],
            price=int(d["price"]),
            product_text=d["product_text"],
            product_photo=d["product_photo"],
            link_mode=d["link_mode"],
            channel_id=d["channel_id"],
            static_link=d["static_link"],
            sales_enabled=d["sales_enabled"] == "1",
        )


class ShopSettings:
    def __init__(self, redis: Redis, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.redis = redis
        self.sf = session_factory
        self._local: tuple[float, Shop] | None = None

    async def get(self) -> Shop:
        now = time.monotonic()
        if self._local and now - self._local[0] < LOCAL_TTL:
            return self._local[1]
        raw = await self.redis.hgetall(KEY)
        if not raw:
            raw = await self._load()
        shop = Shop.from_raw(raw)
        self._local = (now, shop)
        return shop

    async def _load(self) -> dict[str, str]:
        async with self.sf() as s:
            raw = {**DEFAULTS, **(await misc.all_settings(s))}
        async with self.redis.pipeline(transaction=True) as p:
            p.hset(KEY, mapping=raw)
            p.expire(KEY, TTL)
            await p.execute()
        return raw

    async def set(self, key: str, value: str, admin_id: int) -> None:
        if key not in DEFAULTS:
            raise KeyError(key)
        async with self.sf() as s:
            old = (await misc.all_settings(s)).get(key, DEFAULTS[key])
            await misc.set_setting(s, key, value, admin_id)
            await misc.audit(s, admin_id, "setting_change", key=key, old=old[:500], new=value[:500])
            await s.commit()
        self._local = None
        await self.redis.delete(KEY)
