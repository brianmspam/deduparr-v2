"""Config endpoints — CRUD for key-value config store."""

import os
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.config import Config
from app.services.plex_db_service import PlexDbService

router = APIRouter()
logger = logging.getLogger(__name__)

SENSITIVE_KEYS = {"plex_auth_token", "radarr_api_key", "sonarr_api_key"}


class ConfigUpdateRequest(BaseModel):
    config: dict[str, str | None]


@router.get("")
async def get_all_config(db: AsyncSession = Depends(get_db)):
    """Get all configuration values (secrets masked)."""
    result = await db.execute(select(Config))
    configs = result.scalars().all()

    data: dict[str, Any] = {}
    for c in configs:
        if c.key in SENSITIVE_KEYS and c.value:
            data[c.key] = "********"
        else:
            data[c.key] = c.value
    return data


@router.put("")
async def update_config(request: ConfigUpdateRequest, db: AsyncSession = Depends(get_db)):
    """Update configuration values."""
    for key, value in request.config.items():
        result = await db.execute(select(Config).where(Config.key == key))
        config = result.scalar_one_or_none()
        if config:
            config.value = value
        else:
            db.add(Config(key=key, value=value))
    await db.commit()
    return {"status": "success"}


@router.get("/libraries")
async def get_plex_libraries(db: AsyncSession = Depends(get_db)):
    """Get available Plex libraries using stored credentials."""
    result = await db.execute(select(Config).where(Config.key == "plex_url"))
    url_config = result.scalar_one_or_none()
    result = await db.execute(select(Config).where(Config.key == "plex_auth_token"))
    token_config = result.scalar_one_or_none()

    if not url_config or not token_config or not url_config.value or not token_config.value:
        raise HTTPException(status_code=400, detail="Plex not configured")

    from app.services.plex_api_service import PlexApiService

    try:
        service = PlexApiService(url_config.value, token_config.value)
        return service.get_libraries()
    except Exception as e:
        logger.error(f"Failed to get Plex libraries: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to connect to Plex: {e}")


@router.post("/plex-db/copy-local")
async def copy_plex_db_to_local(db: AsyncSession = Depends(get_db)):
    """
    Copy Plex DB from the configured path to a local directory inside the container.
    Uses the stored 'plex_db_path' config key to know where the DB lives.
    Returns the new local DB path.
    """
    # Look up plex_db_path from config store
    result = await db.execute(select(Config).where(Config.key == "plex_db_path"))
    db_path_config = result.scalar_one_or_none()

    if not db_path_config or not db_path_config.value:
        raise HTTPException(status_code=400, detail="Plex DB path (plex_db_path) is not configured")

    try:
        service = PlexDbService(db_path_config.value, db_session=db)
        local_path = await service.copy_db_to_local()
        return {"local_path": local_path}
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to copy Plex DB to local: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Copy failed: {e}")

@router.get("/plex-db/status")
async def get_plex_db_status(db: AsyncSession = Depends(get_db)):
    """
    Check whether the configured Plex DB file exists and return its size.
    Uses the 'plex_db_path' config key.
    """
    result = await db.execute(select(Config).where(Config.key == "plex_db_path"))
    db_path_config = result.scalar_one_or_none()

    if not db_path_config or not db_path_config.value:
        raise HTTPException(status_code=400, detail="Plex DB path (plex_db_path) is not configured")

    db_path = db_path_config.value

    # Check existence and size inside the container filesystem
    if not os.path.isfile(db_path):
        raise HTTPException(status_code=404, detail=f"Plex DB not found at {db_path}")

    size_bytes = os.path.getsize(db_path)
    return {
        "path": db_path,
        "size_bytes": size_bytes,
        "size_mb": round(size_bytes / (1024 * 1024), 2),
    }
