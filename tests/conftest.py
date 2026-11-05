from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest_asyncio

from app.bot import App, build_app
from app.config import Config
from app.db.models import Base
from app.db.repositories import misc
from tests.fake_tg import FakeTelegram, Sim

OWNER = 1000
ADMIN2 = 1001
TEST_DB = os.getenv("TEST_DATABASE_URL", "postgresql+asyncpg://bot:bot@localhost:5432/bot_test")
TEST_REDIS = os.getenv("TEST_REDIS_URL", "redis://localhost:6379/15")


def make_config(**over: object) -> Config:
    base = dict(
        bot_token="42:TEST",
        owner_id=OWNER,
        database_url=TEST_DB,
        redis_url=TEST_REDIS,
        user_rate_limit=1000,
        receipts_per_minute=1000,
        log_json=False,
    )
    base.update(over)
    return Config(**base)  # type: ignore[arg-type]


async def make_app(fake: FakeTelegram, **over: object) -> App:
    app = build_app(make_config(**over), session=fake)
    async with app.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await app.redis.flushdb()
    async with app.sf() as s:
        await misc.add_admin(s, ADMIN2, "Admin2", OWNER)
        await s.commit()
    await app.startup()
    return app


@pytest_asyncio.fixture
async def fake() -> FakeTelegram:
    return FakeTelegram()


@pytest_asyncio.fixture
async def app(fake: FakeTelegram) -> AsyncIterator[App]:
    a = await make_app(fake)
    yield a
    await a.shutdown()


@pytest_asyncio.fixture
async def sim(app: App) -> Sim:
    return Sim(app.bot, app.dp)
