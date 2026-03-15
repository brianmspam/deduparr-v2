"""Config endpoints — CRUD for key-value config store."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.config import Config

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

    data = {}
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
