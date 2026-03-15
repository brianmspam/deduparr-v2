"""Setup endpoints — Plex OAuth, connection tests."""

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

# In-memory store for active PIN login objects
_pin_logins: dict[str, Any] = {}


class PlexCallbackRequest(BaseModel):
    pin_id: str


class PlexServerRequest(BaseModel):
    token: str


@router.get("/plex/auth-url")
async def get_plex_auth_url():
    """Initiate Plex OAuth — returns PIN and auth URL."""
    from app.services.plex_api_service import PlexApiService

    result = await PlexApiService.initiate_oauth()
    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "OAuth failed"))

    pin_login = result.pop("_pin_login", None)
    pin_id = result.get("pin_id", "")
    if pin_login:
        _pin_logins[pin_id] = pin_login

    return result


@router.post("/plex/callback")
async def plex_oauth_callback(request: PlexCallbackRequest, db: AsyncSession = Depends(get_db)):
    """Check if Plex OAuth is complete and store the token."""
    from app.services.plex_api_service import PlexApiService

    pin_id = request.pin_id
    pin_login = _pin_logins.get(pin_id)
    if not pin_login:
        raise HTTPException(status_code=404, detail="PIN not found or expired")

    token = PlexApiService.check_oauth(pin_login)
    if not token:
        return {"success": False, "message": "Authentication not yet complete"}

    # Store token in config
    result = await db.execute(select(Config).where(Config.key == "plex_auth_token"))
    config = result.scalar_one_or_none()
    if config:
        config.value = token
    else:
        db.add(Config(key="plex_auth_token", value=token))
    await db.commit()

    _pin_logins.pop(pin_id, None)
    return {"success": True, "message": "Plex authentication complete"}


@router.post("/plex/test")
async def test_plex_connection(db: AsyncSession = Depends(get_db)):
    """Test Plex server connection using saved config."""
    from app.services.plex_api_service import PlexApiService

    # Read saved config from database
    url_row = await db.execute(select(Config).where(Config.key == "plex_url"))
    url_config = url_row.scalar_one_or_none()
    token_row = await db.execute(select(Config).where(Config.key == "plex_auth_token"))
    token_config = token_row.scalar_one_or_none()

    if not url_config or not url_config.value:
        return {"success": False, "message": "Plex URL not configured. Please enter and save a Plex URL first."}
    if not token_config or not token_config.value:
        return {"success": False, "message": "Plex auth token not found. Please authenticate with OAuth first."}

    service = PlexApiService(url_config.value, token_config.value)
    result = service.test_connection()
    if result.get("success"):
        return {
            "success": True,
            "message": f"Connected to {result.get('server_name', 'Plex')} (v{result.get('version', '?')}, {result.get('platform', '?')})",
        }
    else:
        return {"success": False, "message": result.get("error", "Connection failed")}


@router.post("/plex/servers")
async def get_plex_servers(request: PlexServerRequest):
    """Get available Plex servers for the given token."""
    from app.services.plex_api_service import PlexApiService

    servers = PlexApiService.get_servers_for_token(request.token)
    return {"servers": servers}


@router.get("/status")
async def get_setup_status(db: AsyncSession = Depends(get_db)):
    """Get setup completion status."""
    required_keys = ["plex_auth_token", "plex_url"]
    missing = []

    for key in required_keys:
        result = await db.execute(select(Config).where(Config.key == key))
        config = result.scalar_one_or_none()
        if not config or not config.value:
            missing.append(key)

    return {
        "is_complete": len(missing) == 0,
        "missing_required": missing,
    }
