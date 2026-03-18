"""
Scan orchestrator — coordinates scanning via Plex API or SQLite direct query.
"""

import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.duplicate import DuplicateFile, DuplicateSet, DuplicateStatus, MediaType
from app.services.scoring_engine import ScoringEngine
from app.services.plex_db_service import PlexDbService, LOCAL_PLEX_DB_DIR

logger = logging.getLogger(__name__)


class ScanOrchestrator:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.scoring_engine = ScoringEngine(db)

    async def scan_api(
        self,
        plex_url: str,
        plex_token: str,
        library_names: list[str],
    ) -> dict[str, Any]:
        from app.services.plex_api_service import PlexApiService

        service = PlexApiService(plex_url, plex_token)
        all_duplicates: list[dict[str, Any]] = []
        for lib_name in library_names:
            try:
                dups = service.find_duplicates(lib_name)
                all_duplicates.extend(dups)
            except Exception as e:
                logger.error(f"Failed scanning library '{lib_name}' via API: {e}")

        return await self._process_results(all_duplicates, "api")

    async def scan_sqlite(
        self,
        db_path: str,
        library_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Scan Plex SQLite DB for duplicates.

        Prefers a local copy of the DB in the local Plex DB directory if present.
        If not present, it will best-effort copy from the configured path,
        then fall back to scanning the original path if the copy fails.
        """
        service = PlexDbService(db_path, db_session=self.db)
        all_duplicates: list[dict[str, Any]] = []

        # Prefer local copy if it exists
        base_name = Path(db_path).name
        local_db = LOCAL_PLEX_DB_DIR / base_name
        if local_db.is_file():
            service.db_path = str(local_db)
            logger.info("Using existing local Plex DB copy at %s", service.db_path)
        else:
            # Best-effort attempt to copy to local
            try:
                local_path = await service.copy_db_to_local()
                logger.info("Copied Plex DB to local path for scan: %s", local_path)
            except Exception as e:
                logger.warning("Proceeding without local Plex DB copy: %s", e)

        if library_names:
            for lib_name in library_names:
                try:
                    dups = service.find_duplicates(lib_name)
                    all_duplicates.extend(dups)
                except Exception as e:
                    logger.error(f"Failed scanning library '{lib_name}' via SQLite: {e}")
        else:
            all_duplicates = service.find_duplicates()

        return await self._process_results(all_duplicates, "sqlite")

    async def _process_results(
        self, raw_duplicates: list[dict[str, Any]], method: str
    ) -> dict[str, Any]:
        if not raw_duplicates:
            return {"sets_found": 0, "files_found": 0, "space_reclaimable": 0}

        # Score and rank
        ranked = await self.scoring_engine.rank_all_groups(
            raw_duplicates, group_key="metadata_id"
        )

        # Group by metadata_id for storing
        from collections import defaultdict

        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in ranked:
            groups[r["metadata_id"]].append(r)

        sets_created = 0
        files_created = 0
        total_space = 0

        for metadata_id, group_files in groups.items():
            first = group_files[0]
            media_type = (
                MediaType.MOVIE
                if first.get("media_type") == "movie"
                else MediaType.EPISODE
            )

            # Check if set already exists
            result = await self.db.execute(
                select(DuplicateSet).where(DuplicateSet.plex_item_id == metadata_id)
            )
            existing = result.scalar_one_or_none()

            if existing:
                # Delete old files for this set and re-create
                await self.db.execute(
                    delete(DuplicateFile).where(DuplicateFile.set_id == existing.id)
                )
                dup_set = existing
                dup_set.title = first.get("title", "")
                dup_set.scan_method = method
                dup_set.status = DuplicateStatus.PENDING
            else:
                dup_set = DuplicateSet(
                    plex_item_id=metadata_id,
                    title=first.get("title", ""),
                    media_type=media_type,
                    scan_method=method,
                )
                self.db.add(dup_set)
                sets_created += 1

            await self.db.flush()

            space_reclaimable = 0
            for f in group_files:
                score_breakdown = {
                    "codec": f.get("codec", ""),
                    "container": f.get("container", ""),
                    "resolution": f"{f.get('width', 0)}x{f.get('height', 0)}",
                    "bitrate": f.get("bitrate", 0),
                    "codec_score": f.get("codec_score", 0),
                    "container_score": f.get("container_score", 0),
                    "resolution_score": f.get("resolution_score", 0),
                    "size_score": f.get("size_score", 0),
                    "custom_modifier": f.get("custom_modifier", 0),
                    "total_score": f.get("total_score", 0),
                }

                is_keep = f.get("action") == "KEEP"
                dup_file = DuplicateFile(
                    set_id=dup_set.id,
                    file_path=f.get("file_path", ""),
                    file_size=f.get("file_size", 0),
                    score=f.get("total_score", 0),
                    keep=is_keep,
                    file_metadata=json.dumps(score_breakdown),
                )
                self.db.add(dup_file)
                files_created += 1

                if not is_keep:
                    space_reclaimable += f.get("file_size", 0)

            dup_set.space_to_reclaim = space_reclaimable
            total_space += space_reclaimable

        await self.db.commit()

        return {
            "sets_found": sets_created,
            "files_found": files_created,
            "space_reclaimable": total_space,
        }

    async def get_scan_status(self) -> dict[str, Any]:
        from sqlalchemy import func

        result = await self.db.execute(select(func.count(DuplicateSet.id)))
        total_sets = result.scalar() or 0

        result = await self.db.execute(
            select(func.count(DuplicateSet.id)).where(
                DuplicateSet.status == DuplicateStatus.PENDING
            )
        )
        pending_sets = result.scalar() or 0

        result = await self.db.execute(
            select(func.coalesce(func.sum(DuplicateSet.space_to_reclaim), 0))
        )
        total_space = result.scalar() or 0

        return {
            "total_sets": total_sets,
            "pending_sets": pending_sets,
            "space_reclaimable": total_space,
        }
