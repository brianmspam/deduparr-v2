import os
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from app.core.config import settings

engine = create_async_engine(
    settings.database_url.replace("sqlite://", "sqlite+aiosqlite://"),
    echo=settings.debug,
    future=True,
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()


def utc_now():
    return datetime.now(timezone.utc)


async def init_db():
    from sqlalchemy import text

    parsed = urlparse(settings.database_url)
    db_path = parsed.path
    if db_path.startswith("//"):
        db_path = db_path[1:]

    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    if not os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE IF NOT EXISTS _init (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()

    async with engine.begin() as conn:
        from app.models import (  # noqa: F401
            Config,
            DeletionHistory,
            DuplicateFile,
            DuplicateSet,
            ScoringRule,
        )

        await conn.run_sync(Base.metadata.create_all)

        await conn.execute(text("PRAGMA journal_mode = WAL"))
        await conn.execute(text("PRAGMA synchronous = NORMAL"))
        await conn.execute(text("PRAGMA cache_size = -64000"))
        await conn.execute(text("PRAGMA temp_store = MEMORY"))


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
