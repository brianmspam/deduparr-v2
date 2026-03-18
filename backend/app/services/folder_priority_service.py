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

        # Derive a "top-level" folder in SQL, but still count in Python.
        # Example:
        #   /mnt/media/Movies/MovieName/file.mkv -> /mnt/media/Movies/MovieName
        # This logic assumes POSIX-style paths; adjust for Windows if needed.
        query = """
        SELECT
            mp.file AS file_path,
            -- first split off the directory part
            CASE
                WHEN instr(mp.file, '/') = 0 THEN mp.file
                ELSE substr(mp.file, 1, length(mp.file) - instr(reverse(mp.file), '/') )
            END AS full_folder
        FROM media_parts mp
        JOIN media_items mi ON mp.media_item_id = mi.id
        JOIN metadata_items mdi ON mi.metadata_item_id = mdi.id
        WHERE mp.deleted_at IS NULL
          AND mi.deleted_at IS NULL
          AND mdi.metadata_type IN (1, 4);  -- movies, episodes
        """

        # If your SQLite really doesn’t support reverse(), comment the CASE above
        # and just use: SELECT mp.file AS file_path, mp.file AS full_folder

        cursor = conn.execute(query)
        rows = cursor.fetchall()
        conn.close()

        counts: dict[str, int] = {}

        for r in rows:
            file_path = r["file_path"] or ""
            full_folder = r["full_folder"] or ""

            # Decide what "folder" means. For now, just use full_folder.
            folder = full_folder or os.path.dirname(file_path) or file_path

            counts[folder] = counts.get(folder, 0) + 1

        result = [
            {"folder": folder, "file_count": count}
            for folder, count in counts.items()
            if count >= min_count
        ]
        result.sort(key=lambda x: x["file_count"], reverse=True)
        return result
