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

        # ← NEW: sweep for already-missing files and mark those sets processed too
    await pipeline.mark_missing_files_as_processed()

    return BulkDeleteResult(
        status="ok",
        deleted_files=deleted_files,
        space_freed=space_freed,
        deleted_file_ids=deleted_file_ids,
    )



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


class SetStatusUpdate(BaseModel):
    status: str  # "pending" | "approved" | "rejected" | "processed"


@router.patch("/duplicates/{set_id}/status")
async def update_set_status(
    set_id: int,
    body: SetStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DuplicateSet).where(DuplicateSet.id == set_id)
    )
    dup_set = result.scalar_one_or_none()
    if not dup_set:
        raise HTTPException(status_code=404, detail="Set not found")

    try:
        dup_set.status = DuplicateStatus(body.status)  # ← FIXED: cast to enum
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{body.status}'. Must be one of: {[s.value for s in DuplicateStatus]}",
        )

    await db.commit()
    return {"id": dup_set.id, "status": dup_set.status.value}


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


# FIX: only preview files from APPROVED sets
@router.get("/delete/preview")
async def preview_bulk_delete(db: AsyncSession = Depends(get_db)):
    from app.services.deletion_pipeline import DeletionPipeline

    result = await db.execute(
        select(DuplicateSet)
        .options(selectinload(DuplicateSet.files))
        .where(DuplicateSet.status == DuplicateStatus.APPROVED)
    )
    sets = result.scalars().unique().all()

    pipeline = DeletionPipeline(db, dry_run=False)

    items: list[dict] = []
    total_space = 0

    for dup_set in sets:
        if not any(not f.keep for f in dup_set.files):
            continue

        preview = await pipeline.preview_deletion(dup_set.id)

        files_section = preview.get("delete") or []          # ← FIXED: was "files_to_delete" / "files"
        space_to_free = preview.get("space_to_reclaim") or 0 # ← FIXED: was "space_to_free"

        for f in files_section:
            items.append({
                "id": f["id"],
                "set_id": dup_set.id,
                "title": dup_set.title,
                "file_path": f["file_path"],
                "file_size": f["file_size"],
            })
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


# FIX: single handler, APPROVED only
@router.post("/delete", response_model=BulkDeleteResult)
async def delete_all_non_keep_files(db: AsyncSession = Depends(get_db)):
    from app.services.deletion_pipeline import DeletionPipeline

    result = await db.execute(
        select(DuplicateSet.id).where(DuplicateSet.status == DuplicateStatus.APPROVED)
    )
    set_ids = [row[0] for row in result.fetchall()]

    if not set_ids:
        return BulkDeleteResult(status="ok", deleted_files=0, space_freed=0, deleted_file_ids=[])

    pipeline = DeletionPipeline(db, dry_run=False)

    deleted_files = 0
    space_freed = 0
    deleted_file_ids: list[int] = []

    for set_id in set_ids:
        res = await pipeline.delete_set(set_id)
        file_results = res.get("results", [])                        # ← FIXED: was "deleted_files"
        deleted_files += len([r for r in file_results if r.get("success")])
        space_freed += sum(                                           # ← FIXED: was "space_freed"
            r.get("file_size", 0) for r in file_results if r.get("success")
        )
        deleted_file_ids.extend(                                      # ← FIXED: was "deleted_file_ids"
            r["file_id"] for r in file_results if r.get("success")
        )

    return BulkDeleteResult(
        status="ok",
        deleted_files=deleted_files,
        space_freed=space_freed,
        deleted_file_ids=deleted_file_ids,
    )

