# app/services/folder_priority_service.py
import os
import sqlite3
from typing import Any


class FolderStatsService:
    def __init__(self, plex_db_path: str):
        self.db_path = plex_db_path

    def get_folder_counts(self, min_count: int) -> list[dict[str, Any]]:
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row

        # Just select the file paths; we’ll group by folder in Python
        query = """
        SELECT
            mp.file AS file_path
        FROM media_parts mp
        JOIN media_items mi ON mp.media_item_id = mi.id
        JOIN metadata_items mdi ON mi.metadata_item_id = mdi.id
        WHERE mp.deleted_at IS NULL
          AND mi.deleted_at IS NULL
          AND mdi.metadata_type IN (1, 4);  -- movies, episodes
        """

        cursor = conn.execute(query)
        rows = cursor.fetchall()
        conn.close()

        # Group by folder
        counts: dict[str, int] = {}
        for r in rows:
            file_path = r["file_path"] or ""
            folder = os.path.dirname(file_path) or file_path
            counts[folder] = counts.get(folder, 0) + 1

        # Filter by min_count and sort descending
        result = [
            {"folder": folder, "file_count": count}
            for folder, count in counts.items()
            if count >= min_count
        ]
        result.sort(key=lambda x: x["file_count"], reverse=True)
        return result
