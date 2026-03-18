import sqlite3
from pathlib import Path
from typing import Any

class FolderStatsService:
    def __init__(self, plex_db_path: str):
        self.db_path = plex_db_path

    def get_folder_counts(self, min_count: int) -> list[dict[str, Any]]:
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row

        # Use media_parts.file to derive folders
        query = """
        SELECT
            substr(mp.file, 1, length(mp.file) - instr(reverse(mp.file), '/') + 1) AS folder,
            COUNT(*) AS file_count
        FROM media_parts mp
        JOIN media_items mi ON mp.media_item_id = mi.id
        JOIN metadata_items mdi ON mi.metadata_item_id = mdi.id
        WHERE mp.deleted_at IS NULL
          AND mi.deleted_at IS NULL
          AND mdi.metadata_type IN (1, 4) -- movies, episodes
        GROUP BY folder
        HAVING file_count >= ?
        ORDER BY file_count DESC;
        """

        cursor = conn.execute(query, (min_count,))
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows
