"""Ilova konfiguratsiyasi. Barcha maxfiy qiymatlar faqat .env / muhit o'zgaruvchilaridan olinadi."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    owner_id: int
    telegram_api_url: str = ""            # ixtiyoriy: o'z Bot API serveringiz (yoki test serveri)

    mode: Literal["webhook", "polling"] = "polling"
    webhook_url: str = ""                 # https://bot.example.uz
    webhook_path: str = "/tg/webhook"
    webhook_secret: str = ""
    web_host: str = "0.0.0.0"
    web_port: int = 8080
    web_workers: int = 1                  # webhook jarayonlari soni (tavsiya: CPU yadrolari soni)

    database_url: str = "postgresql+asyncpg://bot:bot@localhost:5432/bot"
    db_pool_size: int = 20
    db_max_overflow: int = 10
    redis_url: str = "redis://localhost:6379/0"
    redis_pool_size: int = 100

    timezone: str = "Asia/Tashkent"
    log_level: str = "INFO"
    log_json: bool = True
    sentry_dsn: str = ""

    # Biznes parametrlari
    pending_reminder_minutes: int = 50     # shuncha daqiqada ko'rilmagan to'lov haqida eslatma
    invite_link_hours: int = 24            # bir martalik havola amal qilish muddati
    broadcast_rate: int = 25               # broadcast: sekundiga xabar (Telegram limiti ~30)
    user_rate_limit: int = 4               # bitta userdan sekundiga maksimal update
    receipts_per_minute: int = 3
    max_receipt_mb: int = 10


@lru_cache
def get_config() -> Config:
    return Config()  # type: ignore[call-arg]
