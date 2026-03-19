# app/services/folder_priority_service.py
import os
import sqlite3
from typing import Any, Dict, List


class FolderStatsService:
    def __init__(self, plex_db_path: str):
        self.db_path = plex_db_path

    def _group_folder(self, file_path: str, group_level: int) -> str:
        """
        Group a file path by the first `group_level` path segments.

        Example:
          file_path = "/mnt/media/Movies/4K/MovieName/file.mkv"
          group_level = 3  -> "/mnt/media/Movies"
          group_level = 4  -> "/mnt/media/Movies/4K"
        """
        # Normalize and split on "/" (Plex DB paths are POSIX-like even on Windows)
        parts = [p for p in file_path.split("/") if p]
        if not parts:
            return file_path

        # Keep the first `group_level` parts
        top_parts = parts[:group_level]
        prefix = "/" if file_path.startswith("/") else ""
        return prefix + "/".join(top_parts)

    def get_folder_counts(
        self,
        min_count: int,
        group_level: int = 3,
    ) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row

        # Get file paths for all movie/episode media_parts
        query = """
        SELECT
            mp.file AS file_path
        FROM media_parts mp
        JOIN media_items mi ON mp.media_item_id = mi.id
        JOIN metadata_items mdi ON mi.metadata_item_id = mdi.id
        WHERE mp.deleted_at IS NULL
          AND mi.deleted_at IS NULL
          AND mdi.metadata_type IN (1, 4);
        """

        cursor = conn.execute(query)
        rows = cursor.fetchall()
        conn.close()

        counts: Dict[str, int] = {}

        for r in rows:
            file_path = r["file_path"] or ""
            # This determines which “top level” folder gets the count.
            group_folder = self._group_folder(file_path, group_level)
            counts[group_folder] = counts.get(group_folder, 0) + 1

        # Filter and sort
        result = [
            {"folder": folder, "file_count": count}
            for folder, count in counts.items()
            if count >= min_count
        ]
        result.sort(key=lambda x: x["file_count"], reverse=True)
        return result
