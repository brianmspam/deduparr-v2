"""Scan endpoints — start scans, view duplicates, delete files."""
import os
import json
import logging
from typing import Optional, Any, List

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
    method: str = "api"


class DeleteRequest(BaseModel):
    dry_run: bool = True


class FileUpdateRequest(BaseModel):
    keep: bool


class VerifyFilesRequest(BaseModel):
    file_ids: list[int]


class SetStatusUpdate(BaseModel):
    status: str


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


class BulkDeleteResult(BaseModel):
    status: str
    deleted_files: int
    space_freed: int
    deleted_file_ids: list[int]


@router.post("/delete/verify")
async def verify_files(
    request: VerifyFilesRequest,
    db: AsyncSession = Depends(get_db),
):
    """Check which files are missing from disk."""
    result = await db.execute(
        select(DuplicateFile).where(DuplicateFile.id.in_(request.file_ids))
    )
    files = result.scalars().all()

    missing = [f.id for f in files if not os.path.isfile(f.file_path)]
    present = [f.id for f in files if os.path.isfile(f.file_path)]

    return {"missing": missing, "present": present}


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
    search: Optional[str] = Query(None),
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
    if search:                                                         # ← ADD
        query = query.where(DuplicateSet.title.ilike(f"%{search}%"))  # ← ADD

    query = query.order_by(DuplicateSet.found_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    sets = result.scalars().unique().all()

    count_query = select(func.count(DuplicateSet.id))
    if status:
        count_query = count_query.where(DuplicateSet.status == status)
    if media_type:
        count_query = count_query.where(DuplicateSet.media_type == media_type)
    if search:                                                              # ← ADD
        count_query = count_query.where(DuplicateSet.title.ilike(f"%{search}%"))  # ← ADD

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

@router.post("/duplicates/{set_id}/reverify")
async def reverify_set(set_id: int, db: AsyncSession = Depends(get_db)):
    """
    For a PROCESSED set, check if any of its non-kept files still exist on disk.
    If any do, reset the set back to PENDING.
    """
    result = await db.execute(
        select(DuplicateSet).where(DuplicateSet.id == set_id)
    )
    dup_set = result.scalar_one_or_none()
    if not dup_set:
        raise HTTPException(status_code=404, detail="Set not found")

    files_result = await db.execute(
        select(DuplicateFile).where(DuplicateFile.set_id == set_id)
    )
    files = files_result.scalars().all()

    still_exist = [f for f in files if not f.keep and os.path.exists(f.file_path)]

    if still_exist:
        dup_set.status = DuplicateStatus.PENDING
        await db.commit()
        return {
            "reset": True,
            "reason": f"{len(still_exist)} file(s) still exist on disk",
            "files": [f.file_path for f in still_exist],
        }

    return {"reset": False, "reason": "All non-kept files are already gone"}

@router.post("/duplicates/reverify-all-processed")
async def reverify_all_processed(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DuplicateSet).where(DuplicateSet.status == DuplicateStatus.PROCESSED)
    )
    sets = result.scalars().all()
    reset_count = 0
    for s in sets:
        files_result = await db.execute(
            select(DuplicateFile).where(
                DuplicateFile.set_id == s.id,
                DuplicateFile.keep == False,
            )
        )
        files = files_result.scalars().all()
        if any(os.path.exists(f.file_path) for f in files):
            s.status = DuplicateStatus.PENDING
            reset_count += 1
    await db.commit()
    return {"reset_count": reset_count}


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


@router.patch("/duplicates/{set_id}/status")
async def update_set_status(
    set_id: int,
    body: SetStatusUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update approval status for a duplicate set."""
    result = await db.execute(
        select(DuplicateSet).where(DuplicateSet.id == set_id)
    )
    dup_set = result.scalar_one_or_none()
    if not dup_set:
        raise HTTPException(status_code=404, detail="Set not found")

    try:
        dup_set.status = DuplicateStatus(body.status)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{body.status}'. Must be one of: {[s.value for s in DuplicateStatus]}",
        )

    await db.commit()
    return {"id": dup_set.id, "status": dup_set.status.value}

@router.get("/delete/preview")
async def preview_bulk_delete(db: AsyncSession = Depends(get_db)):
    """Combined preview of all files that would be deleted by bulk Start Delete."""
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
        files_section = preview.get("delete") or []
        space_to_free = preview.get("space_to_reclaim") or 0

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

class BulkApproveRequest(BaseModel):
    set_ids: Optional[List[int]] = None  # None = approve ALL pending

@router.post("/duplicates/approve-all-pending")
async def approve_all_pending(
    body: BulkApproveRequest = BulkApproveRequest(),
    db: AsyncSession = Depends(get_db),
):
    query = select(DuplicateSet).where(DuplicateSet.status == DuplicateStatus.PENDING)
    if body.set_ids:
        query = query.where(DuplicateSet.id.in_(body.set_ids))
    result = await db.execute(query)
    sets = result.scalars().all()
    for s in sets:
        s.status = DuplicateStatus.APPROVED
    await db.commit()
    return {"approved": len(sets)}




@router.post("/delete", response_model=BulkDeleteResult)
async def delete_all_non_keep_files(db: AsyncSession = Depends(get_db)):
    """Bulk delete non-KEEP files from all APPROVED sets."""
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
        file_results = res.get("results", [])
        deleted_files += len([r for r in file_results if r.get("success")])
        space_freed += sum(
            r.get("file_size", 0) for r in file_results if r.get("success")
        )
        deleted_file_ids.extend(
            r["file_id"] for r in file_results if r.get("success")
        )

    # Sweep for already-missing files and mark those sets processed too
    await pipeline.mark_missing_files_as_processed()

    return BulkDeleteResult(
        status="ok",
        deleted_files=deleted_files,
        space_freed=space_freed,
        deleted_file_ids=deleted_file_ids,
    )
