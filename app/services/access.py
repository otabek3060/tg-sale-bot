"""Kim admin, kim bloklangan — Redis to'plamlarida (SISMEMBER O(1)), DB'ga har so'rovda bormaymiz."""
from __future__ import annotations

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repositories import misc, users

ADMINS_KEY = "cache:admins"
BANNED_KEY = "banned_users"
_SENTINEL = "_"  # bo'sh to'plam ham "yuklangan" deb hisoblanishi uchun


class Access:
    def __init__(self, redis: Redis, session_factory: async_sessionmaker[AsyncSession], owner_id: int) -> None:
        self.redis = redis
        self.sf = session_factory
        self.owner_id = owner_id

    # --- adminlar ---
    async def reload_admins(self) -> set[int]:
        async with self.sf() as s:
            ids = set(await misc.admin_ids(s))
        ids.add(self.owner_id)
        async with self.redis.pipeline(transaction=True) as p:
            p.delete(ADMINS_KEY)
            p.sadd(ADMINS_KEY, _SENTINEL, *map(str, ids))
            p.expire(ADMINS_KEY, 600)
            await p.execute()
        return ids

    async def admin_ids(self) -> set[int]:
        members = await self.redis.smembers(ADMINS_KEY)
        if not members:
            return await self.reload_admins()
        return {int(m) for m in members if m != _SENTINEL}

    async def is_admin(self, user_id: int) -> bool:
        if user_id == self.owner_id:
            return True
        if await self.redis.sismember(ADMINS_KEY, str(user_id)):
            return True
        if not await self.redis.exists(ADMINS_KEY):
            return user_id in await self.reload_admins()
        return False

    def is_owner(self, user_id: int) -> bool:
        return user_id == self.owner_id

    # --- bloklanganlar ---
    async def rebuild_banned(self) -> None:
        async with self.sf() as s:
            ids = await users.banned_ids(s)
        async with self.redis.pipeline(transaction=True) as p:
            p.delete(BANNED_KEY)
            p.sadd(BANNED_KEY, _SENTINEL, *map(str, ids))
            await p.execute()

    async def is_banned(self, user_id: int) -> bool:
        return bool(await self.redis.sismember(BANNED_KEY, str(user_id)))

    async def set_banned(self, user_id: int, banned: bool) -> None:
        if banned:
            await self.redis.sadd(BANNED_KEY, str(user_id))
        else:
            await self.redis.srem(BANNED_KEY, str(user_id))
