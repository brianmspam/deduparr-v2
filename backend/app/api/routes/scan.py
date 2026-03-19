"""Scan endpoints — start scans, view duplicates, delete files."""

import json
import logging
from typing import Optional
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sqlalchemy.orm import selectinload

from app.api.deps import get_db
from app.models.config import Config
from app.models.duplicate import DuplicateFile, DuplicateSet, DuplicateStatus

router = APIRouter()
logger = logging.getLogger(__name__)


class ScanStartRequest(BaseModel):
    library_names: list[str] = []
    method: str = "api"  # "api" | "sqlite"


class DeleteRequest(BaseModel):
    dry_run: bool = True


class FileUpdateRequest(BaseModel):
    keep: bool


@router.post("/start")
async def start_scan(request: ScanStartRequest, db: AsyncSession = Depends(get_db)):
    """Start a duplicate scan."""
    from app.services.scan_orchestrator import ScanOrchestrator

    orchestrator = ScanOrchestrator(db)

    try:
        if request.method == "sqlite":
            result = await db.execute(select(Config).where(Config.key == "plex_db_path"))
            db_path_config = result.scalar_one_or_none()
            if not db_path_config or not db_path_config.value:
                raise HTTPException(status_code=400, detail="Plex database path not configured")
            scan_result = await orchestrator.scan_sqlite(
                db_path_config.value,
                request.library_names if request.library_names else None,
            )
        else:
            result = await db.execute(select(Config).where(Config.key == "plex_url"))
            url_config = result.scalar_one_or_none()
            result = await db.execute(select(Config).where(Config.key == "plex_auth_token"))
            token_config = result.scalar_one_or_none()
            if not url_config or not token_config or not url_config.value or not token_config.value:
                raise HTTPException(status_code=400, detail="Plex not configured")

            # If no libraries selected, auto-discover all libraries
            library_names = request.library_names
            if not library_names:
                from app.services.plex_api_service import PlexApiService
                service = PlexApiService(url_config.value, token_config.value)
                libs = service.get_libraries()
                library_names = [lib["title"] for lib in libs]
                if not library_names:
                    raise HTTPException(status_code=400, detail="No Plex libraries found")

            scan_result = await orchestrator.scan_api(
                url_config.value, token_config.value, library_names
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Scan failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    return scan_result


@router.get("/status")
async def get_scan_status(db: AsyncSession = Depends(get_db)):
    """Get scan statistics."""
    from app.services.scan_orchestrator import ScanOrchestrator

    orchestrator = ScanOrchestrator(db)
    return await orchestrator.get_scan_status()


@router.get("/duplicates")
async def get_duplicates(
    status: Optional[str] = Query(None),
    media_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List duplicate sets with optional filters."""
    query = select(DuplicateSet).options(selectinload(DuplicateSet.files))

    if status:
        query = query.where(DuplicateSet.status == status)
    if media_type:
        query = query.where(DuplicateSet.media_type == media_type)

    query = query.order_by(DuplicateSet.found_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    sets = result.scalars().unique().all()

    # Get total count
    count_query = select(func.count(DuplicateSet.id))
    if status:
        count_query = count_query.where(DuplicateSet.status == status)
    if media_type:
        count_query = count_query.where(DuplicateSet.media_type == media_type)
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return {
        "total": total,
        "items": [
            {
                "id": s.id,
                "plex_item_id": s.plex_item_id,
                "title": s.title,
                "media_type": s.media_type.value if s.media_type else None,
                "found_at": s.found_at.isoformat() if s.found_at else None,
                "status": s.status.value if s.status else None,
                "space_to_reclaim": s.space_to_reclaim,
                "scan_method": s.scan_method,
                "files": [
                    {
                        "id": f.id,
                        "file_path": f.file_path,
                        "file_size": f.file_size,
                        "score": f.score,
                        "keep": f.keep,
                        "file_metadata": json.loads(f.file_metadata) if f.file_metadata else None,
                    }
                    for f in sorted(s.files, key=lambda x: x.score, reverse=True)
                ],
            }
            for s in sets
        ],
    }


@router.get("/duplicates/{set_id}/preview")
async def preview_deletion(set_id: int, db: AsyncSession = Depends(get_db)):
    """Preview deletion for a duplicate set."""
    from app.services.deletion_pipeline import DeletionPipeline

    pipeline = DeletionPipeline(db, dry_run=True)
    return await pipeline.preview_deletion(set_id)


@router.post("/duplicates/{set_id}/delete")
async def delete_duplicates(
    set_id: int,
    request: DeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delete duplicate files in a set."""
    from app.services.deletion_pipeline import DeletionPipeline

    pipeline = DeletionPipeline(db, dry_run=request.dry_run)
    return await pipeline.delete_set(set_id)


@router.patch("/duplicates/{set_id}/files/{file_id}")
async def update_file_keep_flag(
    set_id: int,
    file_id: int,
    request: FileUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Toggle keep/delete flag for a file."""
    result = await db.execute(
        select(DuplicateFile).where(
            DuplicateFile.id == file_id,
            DuplicateFile.set_id == set_id,
        )
    )
    dup_file = result.scalar_one_or_none()
    if not dup_file:
        raise HTTPException(status_code=404, detail="File not found")

    dup_file.keep = request.keep
    await db.commit()

    return {"id": dup_file.id, "keep": dup_file.keep}

@router.post("/delete")
async def delete_all_non_keep_files(
    db: AsyncSession = Depends(get_db),
):
    """
    Bulk delete: for all duplicate sets, call the existing per-set delete endpoint logic.
    This is what the 'Start Delete' button calls.
    """
    from app.services.deletion_pipeline import DeletionPipeline

    # Decide which sets to process. Example: all sets with status APPROVED.
    result = await db.execute(
        select(DuplicateSet.id).where(DuplicateSet.status == DuplicateStatus.APPROVED)
    )
    set_ids = [row[0] for row in result.fetchall()]

    if not set_ids:
        return {
            "status": "ok",
            "deleted_sets": 0,
            "deleted_files": 0,
            "space_freed": 0,
        }

    pipeline = DeletionPipeline(db, dry_run=False)

    total_deleted_sets = 0
    total_deleted_files = 0
    total_space_freed = 0

    for set_id in set_ids:
        # Reuse the same logic as /duplicates/{set_id}/delete
        res = await pipeline.delete_set(set_id)
        total_deleted_sets += 1
        total_deleted_files += res.get("deleted_files", 0)
        total_space_freed += res.get("space_freed", 0)

    return {
        "status": "ok",
        "deleted_sets": total_deleted_sets,
        "deleted_files": total_deleted_files,
        "space_freed": total_space_freed,
    }

class BulkDeleteFile(BaseModel):
    id: int
    set_id: int
    title: str
    file_path: str
    file_size: int

class BulkDeletePreviewResponse(BaseModel):
    items: list[BulkDeleteFile]
    total_files: int
    total_space_to_free: int


@router.get("/delete/preview")
async def preview_bulk_delete(db: AsyncSession = Depends(get_db)):
    """
    Combined preview of all files that would be deleted by bulk 'Start Delete'.

    Rules:
      - Include sets with status PENDING or APPROVED.
      - Within those sets, delete files where keep == False.
    """
    from app.services.deletion_pipeline import DeletionPipeline

    result = await db.execute(
        select(DuplicateSet)
        .options(selectinload(DuplicateSet.files))
        .where(
            DuplicateSet.status.in_(
                [DuplicateStatus.PENDING, DuplicateStatus.APPROVED]
            )
        )
    )
    sets = result.scalars().unique().all()

    pipeline = DeletionPipeline(db, dry_run=True)

    items: list[dict] = []
    total_space = 0

    for dup_set in sets:
        # Skip sets where all files are KEEP
        if not any(not f.keep for f in dup_set.files):
            continue

        preview = await pipeline.preview_deletion(dup_set.id)

        # Handle different possible shapes of preview output
        files_section = (
            preview.get("files_to_delete")
            or preview.get("files")
            or []
        )
        space_to_free = preview.get("space_to_free") or 0

        for f in files_section:
            items.append(
                {
                    "id": f["id"],
                    "set_id": dup_set.id,
                    "title": dup_set.title,
                    "file_path": f["file_path"],
                    "file_size": f["file_size"],
                }
            )
        total_space += space_to_free

    return {
        "items": items,
        "total_files": len(items),
        "total_space_to_free": total_space,
    }

class BulkDeleteResult(BaseModel):
    status: str
    deleted_files: int
    space_freed: int
    deleted_file_ids: list[int]


@router.post("/delete", response_model=BulkDeleteResult)
async def delete_all_non_keep_files(
    db: AsyncSession = Depends(get_db),
):
    """
    Run bulk delete across all selected duplicate sets.
    """
    from app.services.deletion_pipeline import DeletionPipeline

    result = await db.execute(
      select(DuplicateSet.id).where(
          DuplicateSet.status.in_(
              [DuplicateStatus.PENDING, DuplicateStatus.APPROVED]
          )
        )
      )
    set_ids = [row[0] for row in result.fetchall()]

    if not set_ids:
        return BulkDeleteResult(
            status="ok",
            deleted_files=0,
            space_freed=0,
            deleted_file_ids=[],
        )

    pipeline = DeletionPipeline(db, dry_run=False)

    deleted_files = 0
    space_freed = 0
    deleted_file_ids: list[int] = []

    for set_id in set_ids:
        res: dict[str, Any] = await pipeline.delete_set(set_id)
        deleted_files += res.get("deleted_files", 0)
        space_freed += res.get("space_freed", 0)
        deleted_file_ids.extend(res.get("deleted_file_ids", []))

    return BulkDeleteResult(
        status="ok",
        deleted_files=deleted_files,
        space_freed=space_freed,
        deleted_file_ids=deleted_file_ids,
    )