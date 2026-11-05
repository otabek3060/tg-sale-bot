"""Bot, Dispatcher va barcha servislarni yig'ish (composition root).
Testlar ham aynan shu funksiyadan foydalanadi — ishlab chiqarishdagi bilan bir xil konfiguratsiya."""
from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.session.base import BaseSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.redis import DefaultKeyBuilder, RedisStorage
from redis.asyncio import BlockingConnectionPool, Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import Config
from app.db.repositories import misc
from app.db.session import create_engine, create_session_factory
from app.handlers import errors
from app.handlers.admin import broadcast, panel, review, sales, settings, users
from app.handlers.user import buy, fallback, receipt, start
from app.middlewares.core import DbSessionMiddleware, GuardMiddleware, TimingMiddleware
from app.services.access import Access
from app.services.broadcast import Broadcaster
from app.services.notifier import Notifier
from app.services.payments import PaymentService
from app.services.shop_settings import ShopSettings
from app.services.ui import UI
from app.utils.tasks import BackgroundTasks
from app.utils.tg import RetryAfterMiddleware


@dataclass
class App:
    config: Config
    bot: Bot
    dp: Dispatcher
    redis: Redis
    engine: AsyncEngine
    sf: async_sessionmaker[AsyncSession]
    access: Access
    shop: ShopSettings
    notifier: Notifier
    tasks: BackgroundTasks

    async def startup(self) -> None:
        async with self.sf() as s:
            await misc.add_admin(s, self.config.owner_id, "Owner", None, is_owner=True)
            await s.commit()
        await self.access.reload_admins()
        await self.access.rebuild_banned()
        await self.shop.get()  # keshni isitish

    async def shutdown(self) -> None:
        await self.tasks.wait(timeout=20)
        await self.dp.storage.close()
        await self.bot.session.close()
        await self.redis.aclose()
        await self.engine.dispose()


def build_app(
    config: Config,
    *,
    session: BaseSession | None = None,
    redis: Redis | None = None,
    storage: BaseStorage | None = None,
) -> App:
    if session is None and config.telegram_api_url:
        session = AiohttpSession(api=TelegramAPIServer.from_base(config.telegram_api_url))
    bot = Bot(
        token=config.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    bot.session.middleware(RetryAfterMiddleware())

    # BlockingConnectionPool: pul to'lganda xato bermaydi, bo'sh ulanishni kutadi (yuklama cho'qqisida muhim)
    redis = redis or Redis(
        connection_pool=BlockingConnectionPool.from_url(
            config.redis_url, decode_responses=True, max_connections=config.redis_pool_size, timeout=10
        )
    )
    storage = storage or RedisStorage(
        redis=Redis(
            connection_pool=BlockingConnectionPool.from_url(
                config.redis_url, max_connections=config.redis_pool_size, timeout=10
            )
        ),
        key_builder=DefaultKeyBuilder(with_bot_id=True),
        state_ttl=24 * 3600,
        data_ttl=24 * 3600,
    )
    engine = create_engine(config)
    sf = create_session_factory(engine)
    tasks = BackgroundTasks()

    access = Access(redis, sf, config.owner_id)
    shop = ShopSettings(redis, sf)
    ui = UI(bot, redis)
    notifier = Notifier(bot, sf, access)
    payment_service = PaymentService(bot, sf, shop, config)
    broadcaster = Broadcaster(bot, redis, sf, tasks, config.broadcast_rate)

    dp = Dispatcher(
        storage=storage,
        # handler'larga nomi bo'yicha uzatiladigan bog'liqliklar (DI)
        config=config,
        redis=redis,
        sf=sf,
        access=access,
        shop=shop,
        ui=ui,
        notifier=notifier,
        payment_service=payment_service,
        broadcaster=broadcaster,
        tasks=tasks,
    )
    dp.update.outer_middleware(TimingMiddleware())
    dp.update.outer_middleware(GuardMiddleware(redis, access, sf, config.user_rate_limit))
    dp.update.outer_middleware(DbSessionMiddleware(sf))

    # Tartib muhim: admin router'lari (IsAdmin filtri bilan) foydalanuvchi router'laridan oldin,
    # fallback — eng oxirida.
    routers = [
        errors.router,
        panel.router,
        review.router,
        settings.router,
        users.router,
        sales.router,
        broadcast.router,
        start.router,
        buy.router,
        receipt.router,
        fallback.router,
    ]
    for r in routers:
        # Bitta jarayonda bir nechta Dispatcher yaratilsa (testlar, benchmark) — eski bog'lanishni uzamiz
        r._parent_router = None  # noqa: SLF001
    dp.include_routers(*routers)
    return App(config, bot, dp, redis, engine, sf, access, shop, notifier, tasks)
