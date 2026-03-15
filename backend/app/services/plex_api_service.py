"""
Plex API service — connects to Plex via plexapi library.
"""

import logging
from typing import Any

import plexapi
from plexapi.myplex import MyPlexAccount, MyPlexPinLogin
from plexapi.server import PlexServer

plexapi.X_PLEX_PRODUCT = "DeDuparr"

logger = logging.getLogger(__name__)


class PlexApiService:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._server: PlexServer | None = None

    def _get_server(self) -> PlexServer:
        if self._server is None:
            self._server = PlexServer(self.base_url, self.token)
        return self._server

    def test_connection(self) -> dict[str, Any]:
        try:
            server = self._get_server()
            return {
                "success": True,
                "server_name": server.friendlyName,
                "version": server.version,
                "platform": server.platform,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_libraries(self) -> list[dict[str, str]]:
        server = self._get_server()
        libraries = []
        for section in server.library.sections():
            if section.type in ("movie", "show"):
                libraries.append({
                    "key": section.key,
                    "title": section.title,
                    "type": section.type,
                })
        return libraries

    def find_duplicates(self, library_name: str) -> list[dict[str, Any]]:
        server = self._get_server()
        section = server.library.section(library_name)
        results: list[dict[str, Any]] = []

        if section.type == "movie":
            results.extend(self._find_movie_duplicates(section))
        elif section.type == "show":
            results.extend(self._find_episode_duplicates(section))

        return results

    def _find_movie_duplicates(self, section: Any) -> list[dict[str, Any]]:
        duplicates: list[dict[str, Any]] = []
        for movie in section.all():
            if len(movie.media) > 1:
                metadata_id = str(movie.ratingKey)
                title = movie.title
                if movie.year:
                    title = f"{movie.title} ({movie.year})"
                for media in movie.media:
                    file_path = media.parts[0].file if media.parts else ""
                    file_size = media.parts[0].size if media.parts else 0
                    duplicates.append({
                        "metadata_id": metadata_id,
                        "title": title,
                        "media_type": "movie",
                        "codec": media.videoCodec or "",
                        "container": media.container or "",
                        "width": media.width or 0,
                        "height": media.height or 0,
                        "bitrate": media.bitrate or 0,
                        "file_path": file_path,
                        "file_size": file_size or 0,
                        "media_item_id": media.id,
                    })
        return duplicates

    def _find_episode_duplicates(self, section: Any) -> list[dict[str, Any]]:
        duplicates: list[dict[str, Any]] = []
        for show in section.all():
            for episode in show.episodes():
                if len(episode.media) > 1:
                    metadata_id = str(episode.ratingKey)
                    show_title = show.title
                    s_num = str(episode.seasonNumber).zfill(2)
                    e_num = str(episode.episodeNumber).zfill(2)
                    title = f"{show_title} - S{s_num}E{e_num} - {episode.title}"
                    for media in episode.media:
                        file_path = media.parts[0].file if media.parts else ""
                        file_size = media.parts[0].size if media.parts else 0
                        duplicates.append({
                            "metadata_id": metadata_id,
                            "title": title,
                            "media_type": "episode",
                            "codec": media.videoCodec or "",
                            "container": media.container or "",
                            "width": media.width or 0,
                            "height": media.height or 0,
                            "bitrate": media.bitrate or 0,
                            "file_path": file_path,
                            "file_size": file_size or 0,
                            "media_item_id": media.id,
                        })
        return duplicates

    @staticmethod
    async def initiate_oauth() -> dict[str, Any]:
        try:
            pin_login = MyPlexPinLogin(oauth=True)
            pin = pin_login.pin
            auth_url = pin_login.oauthUrl()
            return {
                "success": True,
                "pin": pin,
                "pin_id": str(pin_login.id) if hasattr(pin_login, "id") else str(pin),
                "auth_url": auth_url,
                "_pin_login": pin_login,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def check_oauth(pin_login: MyPlexPinLogin) -> str | None:
        if pin_login.checkLogin():
            return pin_login.token
        return None

    @staticmethod
    def get_servers_for_token(token: str) -> list[dict[str, str]]:
        try:
            account = MyPlexAccount(token=token)
            servers = []
            for resource in account.resources():
                if resource.provides and "server" in resource.provides:
                    servers.append({
                        "name": resource.name,
                        "client_id": resource.clientIdentifier,
                    })
            return servers
        except Exception as e:
            logger.error(f"Failed to get Plex servers: {e}")
            return []

    @staticmethod
    def get_server_connection(token: str, server_name: str) -> str | None:
        try:
            account = MyPlexAccount(token=token)
            resource = account.resource(server_name)
            server = resource.connect()
            return server._baseurl
        except Exception as e:
            logger.error(f"Failed to connect to Plex server '{server_name}': {e}")
            return None
