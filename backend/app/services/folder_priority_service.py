# app/services/folder_priority_service.py
import sqlite3
from typing import Any, Dict, List


class FolderStatsService:
    def __init__(self, plex_db_path: str):
        self.db_path = plex_db_path

    def _group_by_third_segment(self, file_path: str) -> str:
        """
        Group by the first 3 path segments.

        Example:
          /FTP_Input/Plex/MovieLibrary/Zombieland (2009)/file.mkv
          -> /FTP_Input/Plex/MovieLibrary
        """
        # Plex stores POSIX-style paths even for Windows sources
        parts = [p for p in file_path.split("/") if p]
        if not parts:
            return file_path

        # Take first 3 segments; if fewer, take all
        top_parts = parts[:3]
        prefix = "/" if file_path.startswith("/") else ""
        return prefix + "/".join(top_parts)

    def get_folder_counts(self, min_count: int) -> List[Dict[str, Any]]:
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row

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
            folder = self._group_by_third_segment(file_path)
            counts[folder] = counts.get(folder, 0) + 1

        result = [
            {"folder": folder, "file_count": count}
            for folder, count in counts.items()
            if count >= min_count
        ]
        result.sort(key=lambda x: x["file_count"], reverse=True)
        return result
