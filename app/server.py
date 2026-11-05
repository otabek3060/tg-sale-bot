"""Ishga tushirish logikasi (polling / webhook, ko'p jarayonli). Kirish nuqtasi: `python -m app`."""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram.types import BotCommand, BotCommandScopeChat, BotCommandScopeDefault
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from app.bot import App, build_app
from app.config import get_config
from app.utils.logging import setup_logging
from app.utils.timez import set_timezone
from app.worker.scheduler import scheduler_loop

log = logging.getLogger("app")


async def _on_startup(app: App, stop: asyncio.Event) -> None:
    await app.startup()
    await app.bot.set_my_commands([BotCommand(command="start", description="Boshlash")], scope=BotCommandScopeDefault())
    for admin_id in await app.access.admin_ids():
        try:
            await app.bot.set_my_commands(
                [BotCommand(command="start", description="Boshlash"), BotCommand(command="admin", description="Admin panel")],
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception:  # noqa: BLE001 - admin hali /start bosmagan bo'lishi mumkin
            log.warning("set_my_commands failed for admin %s", admin_id)
    app.tasks.spawn(
        scheduler_loop(app.redis, app.sf, app.notifier, app.config.pending_reminder_minutes, stop), name="scheduler"
    )


def _init_sentry(dsn: str) -> None:
    if not dsn:
        return
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=dsn, traces_sample_rate=0.0)
    except ImportError:
        log.warning("sentry-sdk o'rnatilmagan")


async def run_polling(app: App) -> None:
    stop = asyncio.Event()
    try:
        await _on_startup(app, stop)
        await app.bot.delete_webhook(drop_pending_updates=False)
        log.info("Bot polling rejimida ishga tushdi")
        await app.dp.start_polling(app.bot, allowed_updates=app.dp.resolve_used_update_types(), handle_signals=True)
    finally:
        stop.set()
        await app.shutdown()


def run_webhook(app: App, worker: int = 0) -> None:
    cfg = app.config
    stop = asyncio.Event()

    async def on_startup(_: web.Application) -> None:
        await _on_startup(app, stop)
        if worker != 0:
            return  # webhook'ni faqat birinchi worker o'rnatadi
        await app.bot.set_webhook(
            url=cfg.webhook_url.rstrip("/") + cfg.webhook_path,
            secret_token=cfg.webhook_secret or None,
            allowed_updates=app.dp.resolve_used_update_types(),
            max_connections=100,
            drop_pending_updates=False,
        )
        log.info("Webhook o'rnatildi: %s%s", cfg.webhook_url, cfg.webhook_path)

    async def on_shutdown(_: web.Application) -> None:
        stop.set()
        await app.shutdown()

    async def health(_: web.Request) -> web.Response:
        await app.redis.ping()
        return web.json_response({"ok": True, "background_tasks": len(app.tasks)})

    web_app = web.Application()
    web_app.router.add_get("/health", health)
    # handle_in_background=True: Telegram'ga darhol 200 qaytaramiz, update fonda ishlanadi —
    # bitta sekin so'rov boshqalarni kutib turmaydi.
    SimpleRequestHandler(
        dispatcher=app.dp, bot=app.bot, secret_token=cfg.webhook_secret or None, handle_in_background=True
    ).register(web_app, path=cfg.webhook_path)
    setup_application(web_app, app.dp, bot=app.bot)
    web_app.on_startup.append(on_startup)
    web_app.on_shutdown.append(on_shutdown)
    web.run_app(
        web_app,
        host=cfg.web_host,
        port=cfg.web_port,
        access_log=None,
        handle_signals=True,
        reuse_port=cfg.web_workers > 1,  # bir nechta jarayon bitta portni tinglaydi, yadro taqsimlaydi
    )


def _prepare() -> None:
    cfg = get_config()
    setup_logging(cfg.log_level, cfg.log_json)
    set_timezone(cfg.timezone)
    _init_sentry(cfg.sentry_dsn)
    if sys.platform != "win32":
        try:
            import uvloop

            uvloop.install()
        except ImportError:
            pass


def _webhook_worker(worker: int) -> None:
    _prepare()
    run_webhook(build_app(get_config()), worker)


def main() -> None:
    _prepare()
    cfg = get_config()

    if cfg.mode == "webhook":
        if not cfg.webhook_url or not cfg.webhook_secret:
            raise SystemExit("WEBHOOK_URL va WEBHOOK_SECRET .env da bo'lishi shart")
        if cfg.web_workers <= 1 or sys.platform == "win32":
            run_webhook(build_app(cfg))
            return
        # Python bitta jarayonda bitta CPU yadrosidan foydalanadi. Bot stateless (holat Redis/Postgres'da),
        # shuning uchun N ta jarayon = ~N barobar o'tkazuvchanlik.
        import multiprocessing as mp

        ctx = mp.get_context("spawn")
        procs = [ctx.Process(target=_webhook_worker, args=(i,), name=f"bot-worker-{i}") for i in range(cfg.web_workers)]
        for p in procs:
            p.start()
        log.info("%s ta webhook worker ishga tushdi", len(procs))
        for p in procs:
            p.join()
    else:
        async def _run() -> None:
            await run_polling(build_app(cfg))

        asyncio.run(_run())

