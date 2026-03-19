"""DeDuparr v2 — Main FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app import DEDUPARR_VERSION
from app.core.config import settings
from app.core.database import init_db, AsyncSessionLocal
from app.api.routes import config, setup, scoring, stats, scan, system
from app.api.routes.system import setup_log_capture
from app.models.config import Config
from app.services.plex_db_service import PlexDbService


# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Suppress plexapi library noise
logging.getLogger("plexapi").setLevel(logging.CRITICAL)

# Setup in-memory log capture for system page
setup_log_capture()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    await init_db()

    # Best-effort: copy Plex DB to local on startup using configured plex_db_path
    async with AsyncSessionLocal() as session:
        try:
            result = await session.execute(
                select(Config).where(Config.key == "plex_db_path")
            )
            db_path_config = result.scalar_one_or_none()

            if db_path_config and db_path_config.value:
                service = PlexDbService(db_path_config.value, db_session=session)
                local_path = await service.copy_db_to_local()
                logger.info("Copied Plex DB to local path on startup: %s", local_path)
            else:
                logger.info(
                    "Plex DB path (plex_db_path) is not configured; skipping startup copy."
                )
        except Exception as e:
            logger.warning("Failed to copy Plex DB to local on startup: %s", e)

    logger.info("DeDuparr v%s started successfully", DEDUPARR_VERSION)
    yield
    logger.info("DeDuparr shutting down...")


app = FastAPI(
    title="DeDuparr API",
    description="Duplicate media file manager for Plex",
    version=DEDUPARR_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "version": DEDUPARR_VERSION}


# API routes
app.include_router(config.router, prefix="/api/config", tags=["config"])
app.include_router(setup.router, prefix="/api/setup", tags=["setup"])
app.include_router(scoring.router, prefix="/api/scoring", tags=["scoring"])
app.include_router(stats.router, prefix="/api/stats", tags=["stats"])
app.include_router(scan.router, prefix="/api/scan", tags=["scan"])
app.include_router(system.router, prefix="/api", tags=["system"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
