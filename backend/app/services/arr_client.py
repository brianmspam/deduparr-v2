"""
ArrClient — optional Radarr/Sonarr integration.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ArrClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.headers = {"X-Api-Key": self.api_key}
        self._enabled = bool(base_url and api_key)

    async def test_connection(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.base_url}/api/v3/system/status",
                    headers=self.headers,
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
                return {
                    "success": True,
                    "version": data.get("version", ""),
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def remove_file(self, file_path: str) -> bool:
        if not self._enabled: 
           return False
        """Look up a media file by path and trigger a rescan."""
        try:
            async with httpx.AsyncClient() as client:
                # Try to find the movie/series with this file
                resp = await client.get(
                    f"{self.base_url}/api/v3/movie",
                    headers=self.headers,
                    timeout=30,
                )
                if resp.status_code == 200:
                    movies = resp.json()
                    for movie in movies:
                        if movie.get("movieFile", {}).get("path") == file_path:
                            # Trigger rescan for this movie
                            await client.post(
                                f"{self.base_url}/api/v3/command",
                                headers=self.headers,
                                json={
                                    "name": "RescanMovie",
                                    "movieId": movie["id"],
                                },
                                timeout=10,
                            )
                            return True
            return False
        except Exception as e:
            logger.warning(f"Arr file removal failed: {e}")
            return False

    async def trigger_rescan(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.base_url}/api/v3/command",
                    headers=self.headers,
                    json={"name": "RescanMovie"},
                    timeout=10,
                )
                return resp.status_code in (200, 201)
        except Exception as e:
            logger.warning(f"Arr rescan trigger failed: {e}")
            return False
