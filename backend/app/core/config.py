from typing import Optional

from pydantic import ConfigDict
from pydantic_settings import BaseSettings

from app import DEDUPARR_VERSION


class Settings(BaseSettings):
    model_config = ConfigDict(env_file=".env", case_sensitive=False)

    app_name: str = "DeDuparr"
    app_version: str = DEDUPARR_VERSION
    debug: bool = False
    log_level: str = "INFO"

    database_url: str = "sqlite:////config/deduparr.db"

    config_dir: str = "/config"
    media_dir: str = "/media"

    plex_db_path: Optional[str] = None

    enable_scheduled_scans: bool = False
    scan_interval_hours: int = 24


settings = Settings()
