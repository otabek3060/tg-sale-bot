from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import Config


def create_engine(config: Config) -> AsyncEngine:
    return create_async_engine(
        config.database_url,
        pool_size=config.db_pool_size,
        max_overflow=config.db_max_overflow,
        # pool_pre_ping har ulanish olishda qo'shimcha round-trip qiladi (~1 ms) — yuklama ostida qimmat.
        # Uning o'rniga: ulanishlar 5 daqiqada yangilanadi, uzilish xatosida SQLAlchemy pulni o'zi tozalaydi.
        pool_pre_ping=False,
        pool_recycle=300,
        pool_timeout=15,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    # expire_on_commit=False: commit'dan keyin obyektlar o'qilishi mumkin, ulanish pulga qaytadi
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
