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

        # Migrate existing tables — add missing columns
        await _migrate_tables(conn)

        await conn.execute(text("PRAGMA journal_mode = WAL"))
        await conn.execute(text("PRAGMA synchronous = NORMAL"))
        await conn.execute(text("PRAGMA cache_size = -64000"))
        await conn.execute(text("PRAGMA temp_store = MEMORY"))


async def _migrate_tables(conn):
    """Add missing columns to existing tables (SQLite doesn't support ALTER for create_all)."""
    from sqlalchemy import text
    import logging

    logger = logging.getLogger(__name__)

    # Define expected columns: (table, column, SQL type, default)
    migrations = [
        ("scoring_rules", "name", "VARCHAR(255) NOT NULL DEFAULT ''"),
        ("scoring_rules", "pattern", "TEXT NOT NULL DEFAULT ''"),
        ("scoring_rules", "score_modifier", "INTEGER NOT NULL DEFAULT 0"),
        ("scoring_rules", "enabled", "BOOLEAN NOT NULL DEFAULT 1"),
        ("scoring_rules", "created_at", "DATETIME"),
        ("duplicate_sets", "scan_method", "VARCHAR(50)"),
        ("duplicate_sets", "space_to_reclaim", "INTEGER DEFAULT 0"),
        ("duplicate_files", "file_metadata", "TEXT"),
    ]

    for table, column, col_type in migrations:
        try:
            result = await conn.execute(text(f"PRAGMA table_info({table})"))
            existing_columns = {row[1] for row in result.fetchall()}
            if column not in existing_columns:
                logger.info(f"Migrating: adding {column} to {table}")
                await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
        except Exception as e:
            # Table might not exist yet (will be created by create_all)
            logger.debug(f"Migration skipped for {table}.{column}: {e}")


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
