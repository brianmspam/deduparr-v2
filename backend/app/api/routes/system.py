"""System endpoints — health, version, logs."""

import logging
from collections import deque

from fastapi import APIRouter, Query

from app import DEDUPARR_VERSION

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory log buffer
_log_buffer: deque[str] = deque(maxlen=500)


class LogCaptureHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            _log_buffer.append(msg)
        except Exception:
            pass


def setup_log_capture() -> None:
    handler = LogCaptureHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    logging.root.addHandler(handler)


@router.get("/system/version")
async def get_version():
    """Get application version info."""
    return {
        "version": DEDUPARR_VERSION,
        "app_name": "DeDuparr",
    }


@router.get("/system/logs")
async def get_logs(lines: int = Query(100, ge=1, le=500)):
    """Get recent application logs."""
    log_lines = list(_log_buffer)
    return {"lines": log_lines[-lines:]}
