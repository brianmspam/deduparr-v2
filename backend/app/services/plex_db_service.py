"""
Plex database direct query service.
Opens a Plex SQLite database (backup copy) read-only and finds duplicates.
"""

import logging
import sqlite3
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

FIND_DUPLICATES_SQL = """
WITH duplicate_metadata AS (
    SELECT mdi.id AS metadata_id
    FROM metadata_items mdi
    WHERE mdi.media_item_count > 1
      AND mdi.metadata_type IN (1, 4)
),
all_versions AS (
    SELECT
        mdi.id                          AS metadata_id,
        mdi.metadata_type,
        CASE
            WHEN mdi.metadata_type = 1 THEN
                mdi.title || COALESCE(' (' || mdi.year || ')', '')
            WHEN mdi.metadata_type = 4 THEN
                COALESCE(grandparent.title, '') ||
                ' - S' || printf('%02d', COALESCE(parent.[index], 0)) ||
                'E' || printf('%02d', COALESCE(mdi.[index], 0)) ||
                ' - ' || mdi.title
            ELSE mdi.title
        END                             AS media_title,
        CASE mdi.metadata_type
            WHEN 1 THEN 'Movie'
            WHEN 4 THEN 'Episode'
            ELSE 'Other'
        END                             AS media_type,
        ls.name                         AS library_name,
        mi.id                           AS media_item_id,
        mi.container,
        mi.video_codec,
        mi.audio_codec,
        mi.bitrate,
        mi.width,
        mi.height,
        mi.size                         AS mi_size,
        mi.duration,
        mp.id                           AS media_part_id,
        mp.file,
        mp.size                         AS file_size
    FROM duplicate_metadata dm
    INNER JOIN metadata_items mdi ON mdi.id = dm.metadata_id
    INNER JOIN media_items mi     ON mi.metadata_item_id = mdi.id
    INNER JOIN media_parts mp     ON mp.media_item_id = mi.id
    LEFT JOIN library_sections ls ON ls.id = mdi.library_section_id
    LEFT JOIN metadata_items parent      ON parent.id = mdi.parent_id
    LEFT JOIN metadata_items grandparent ON grandparent.id = parent.parent_id
    WHERE mi.deleted_at IS NULL
      AND mp.deleted_at IS NULL
)
SELECT * FROM all_versions
ORDER BY metadata_id, media_item_id;
"""

# Local directory inside the container where we keep a copy of the Plex DB
LOCAL_PLEX_DB_DIR = Path("/app/data/plex_db_local")


class PlexDbService:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def copy_db_to_local(self) -> str:
        """
        Copy Plex DB and related files to a local directory inside the container.
        Returns the local DB path as a string and updates self.db_path.
        """
        if not self.db_path:
            raise ValueError("Plex DB path is not configured.")

        src = Path(self.db_path)
        if not src.is_file():
            raise FileNotFoundError(f"Plex DB not found at {src}")

        LOCAL_PLEX_DB_DIR.mkdir(parents=True, exist_ok=True)

        base = src.name  # e.g. com.plexapp.plugins.library.db
        prefix = base.rsplit(".db", 1)[0]

        for entry in src.parent.iterdir():
            name = entry.name
            if not entry.is_file():
                continue

            # main db
            if name == base:
                shutil.copy2(entry, LOCAL_PLEX_DB_DIR / name)
                continue

            # date‑suffixed backups: com.plexapp.plugins.library.db-YYYY-MM-DD
            if name.startswith(f"{base}-"):
                shutil.copy2(entry, LOCAL_PLEX_DB_DIR / name)
                continue

            # wal/shm variants
            if name.endswith(".db-wal") or name.endswith(".db-shm"):
                if name.startswith(prefix):
                    shutil.copy2(entry, LOCAL_PLEX_DB_DIR / name)

        local_db = LOCAL_PLEX_DB_DIR / base
        if not local_db.is_file():
            raise FileNotFoundError(f"Local Plex DB copy not found at {local_db}")

        self.db_path = str(local_db)
        logger.info("Plex DB copied to local path: %s", self.db_path)
        return self.db_path

    def find_duplicates(self, library_name: str | None = None) -> list[dict[str, Any]]:
        """
        Query the Plex SQLite database for duplicate media items.
        Returns results in the same format as PlexApiService.find_duplicates().
        """
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(FIND_DUPLICATES_SQL)
            raw_rows = [dict(row) for row in cursor.fetchall()]
            conn.close()
        except Exception as e:
            logger.error(f"Failed to query Plex database at {self.db_path}: {e}")
            raise

        if library_name:
            raw_rows = [r for r in raw_rows if r.get("library_name") == library_name]

        # Convert to unified format matching PlexApiService output
        results: list[dict[str, Any]] = []
        for row in raw_rows:
            file_size = row.get("file_size") or row.get("mi_size") or 0
            media_type_raw = row.get("media_type", "Other")
            media_type = "movie" if media_type_raw == "Movie" else "episode"

            results.append({
                "metadata_id": str(row["metadata_id"]),
                "title": row.get("media_title", ""),
                "media_type": media_type,
                "codec": row.get("video_codec", "") or "",
                "container": row.get("container", "") or "",
                "width": row.get("width", 0) or 0,
                "height": row.get("height", 0) or 0,
                "bitrate": row.get("bitrate", 0) or 0,
                "file_path": row.get("file", ""),
                "file_size": file_size,
                "media_item_id": row.get("media_item_id", 0),
                "library_name": row.get("library_name", ""),
            })

        return results

    def test_connection(self) -> dict[str, Any]:
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            cursor = conn.execute(
                "SELECT COUNT(*) FROM metadata_items "
                "WHERE media_item_count > 1 AND metadata_type IN (1, 4)"
            )
            count = cursor.fetchone()[0]
            conn.close()
            return {"success": True, "duplicate_count": count}
        except Exception as e:
            return {"success": False, "error": str(e)}
