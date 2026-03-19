"""
Deletion pipeline — handles file deletion with Plex refresh and optional *arr integration.
"""

import logging
import os
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.duplicate import DuplicateFile, DuplicateSet, DuplicateStatus
from app.models.history import DeletionHistory

logger = logging.getLogger(__name__)


class DeletionPipeline:
    def __init__(self, db: AsyncSession, dry_run: bool = True):
        self.db = db
        self.dry_run = dry_run

    async def delete_file(self, file_id: int) -> dict[str, Any]:
        result = await self.db.execute(
            select(DuplicateFile).where(DuplicateFile.id == file_id)
        )
        dup_file = result.scalar_one_or_none()

        if not dup_file:
            return {"success": False, "error": "File not found"}

        if dup_file.keep:
            return {"success": False, "error": "Cannot delete file marked as KEEP"}

        errors: list[str] = []
        deleted_from_disk = False
        plex_refreshed = False
        deleted_from_arr = False

        # Stage 1: Delete from disk
        if self.dry_run:
            logger.info(f"[DRY RUN] Would delete: {dup_file.file_path}")
            deleted_from_disk = True
        else:
            try:
                if os.path.isfile(dup_file.file_path):
                    os.remove(dup_file.file_path)
                    deleted_from_disk = True
                    logger.info(f"Deleted file: {dup_file.file_path}")
                else:
                    errors.append(f"File not found on disk: {dup_file.file_path}")
            except OSError as e:
                errors.append(f"Failed to delete file: {e}")

        # Stage 2: Refresh Plex
        if deleted_from_disk and not self.dry_run:
            try:
                await self._refresh_plex(dup_file)
                plex_refreshed = True
            except Exception as e:
                errors.append(f"Plex refresh failed: {e}")

        # Stage 3: Optional *arr removal
        try:
            await self._remove_from_arr(dup_file)
            deleted_from_arr = True
        except Exception as e:
            errors.append(str(e))

        # Record history
        history = DeletionHistory(
            duplicate_file_id=dup_file.id,
            deleted_from_disk=deleted_from_disk,
            plex_refreshed=plex_refreshed,
            deleted_from_arr=deleted_from_arr,
            error="; ".join(errors) if errors else None,
        )

        self.db.add(history)
        await self.db.commit()

        return {
            "success": deleted_from_disk,
            "dry_run": self.dry_run,
            "deleted_from_disk": deleted_from_disk,
            "plex_refreshed": plex_refreshed,
            "deleted_from_arr": deleted_from_arr,
            "errors": errors,
        }

    async def delete_set(self, set_id: int) -> dict[str, Any]:
        result = await self.db.execute(
            select(DuplicateSet)
            .options(selectinload(DuplicateSet.files))
            .where(DuplicateSet.id == set_id)
        )
        dup_set = result.scalar_one_or_none()

        if not dup_set:
            return {"success": False, "error": "Set not found"}

        results: list[dict[str, Any]] = []
        for f in dup_set.files:
            if not f.keep:
                res = await self.delete_file(f.id)
                results.append({"file_id": f.id, "file_path": f.file_path, **res})

        all_success = all(r.get("success") for r in results)
        if all_success and not self.dry_run:
            dup_set.status = DuplicateStatus.PROCESSED
            await self.db.commit()

        return {
            "success": all_success,
            "set_id": set_id,
            "files_processed": len(results),
            "results": results,
        }

    async def preview_deletion(self, set_id: int) -> dict[str, Any]:
        result = await self.db.execute(
            select(DuplicateSet)
            .options(selectinload(DuplicateSet.files))
            .where(DuplicateSet.id == set_id)
        )
        dup_set = result.scalar_one_or_none()

        if not dup_set:
            return {"success": False, "error": "Set not found"}

        files_to_delete = [f for f in dup_set.files if not f.keep]
        files_to_keep = [f for f in dup_set.files if f.keep]

        return {
            "set_id": set_id,
            "title": dup_set.title,
            "keep": [
                {
                    "id": f.id,
                    "file_path": f.file_path,
                    "file_size": f.file_size,
                    "score": f.score,
                }
                for f in files_to_keep
            ],
            "delete": [
                {
                    "id": f.id,
                    "file_path": f.file_path,
                    "file_size": f.file_size,
                    "score": f.score,
                }
                for f in files_to_delete
            ],
            "space_to_reclaim": sum(f.file_size for f in files_to_delete),
        }

    async def _refresh_plex(self, dup_file: DuplicateFile) -> None:
        from app.models.config import Config

        result = await self.db.execute(select(Config).where(Config.key == "plex_url"))
        url_config = result.scalar_one_or_none()
        result = await self.db.execute(select(Config).where(Config.key == "plex_auth_token"))
        token_config = result.scalar_one_or_none()

        if not url_config or not token_config:
            logger.warning("Plex not configured — skipping refresh")
            return

        try:
            from app.services.plex_api_service import PlexApiService

            service = PlexApiService(url_config.value, token_config.value)
            server = service._get_server()
            # Find the library section containing this file and refresh
            for section in server.library.sections():
                server.library.section(section.title).update()
                break
        except Exception as e:
            raise RuntimeError(f"Plex refresh failed: {e}")

    async def _remove_from_arr(self, dup_file: DuplicateFile) -> None:
        # Optional — only if *arr services are configured
        from app.models.config import Config

        result = await self.db.execute(select(Config).where(Config.key == "radarr_url"))
        radarr_config = result.scalar_one_or_none()

        result = await self.db.execute(select(Config).where(Config.key == "sonarr_url"))
        sonarr_config = result.scalar_one_or_none()

        if not radarr_config and not sonarr_config:
            return

        # Attempt arr removal via ArrClient
        try:
            from app.services.arr_client import ArrClient

            if radarr_config and radarr_config.value:
                result = await self.db.execute(select(Config).where(Config.key == "radarr_api_key"))
                api_key_config = result.scalar_one_or_none()
                if api_key_config and api_key_config.value:
                    client = ArrClient(radarr_config.value, api_key_config.value)
                    await client.remove_file(dup_file.file_path)
        except Exception as e:
            logger.warning(f"Failed to remove from *arr: {e}")
