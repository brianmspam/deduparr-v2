"""Stats endpoints — dashboard overview and deletion history."""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_db
from app.models.duplicate import DuplicateFile, DuplicateSet, DuplicateStatus
from app.models.history import DeletionHistory

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/dashboard")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)):
    """Dashboard overview statistics."""
    # Total duplicate sets
    result = await db.execute(select(func.count(DuplicateSet.id)))
    total_sets = result.scalar() or 0

    # Pending sets
    result = await db.execute(
        select(func.count(DuplicateSet.id)).where(
            DuplicateSet.status == DuplicateStatus.PENDING
        )
    )
    pending_sets = result.scalar() or 0

    # Processed sets
    result = await db.execute(
        select(func.count(DuplicateSet.id)).where(
            DuplicateSet.status == DuplicateStatus.PROCESSED
        )
    )
    processed_sets = result.scalar() or 0

    # Total space reclaimable
    result = await db.execute(
        select(func.coalesce(func.sum(DuplicateSet.space_to_reclaim), 0)).where(
            DuplicateSet.status == DuplicateStatus.PENDING
        )
    )
    space_reclaimable = result.scalar() or 0

    # Total files
    result = await db.execute(select(func.count(DuplicateFile.id)))
    total_files = result.scalar() or 0

    # Total deletions
    result = await db.execute(select(func.count(DeletionHistory.id)))
    total_deletions = result.scalar() or 0

    # Space freed (from processed sets)
    result = await db.execute(
        select(func.coalesce(func.sum(DuplicateSet.space_to_reclaim), 0)).where(
            DuplicateSet.status == DuplicateStatus.PROCESSED
        )
    )
    space_freed = result.scalar() or 0

    # Scan method distribution
    result = await db.execute(
        select(DuplicateSet.scan_method, func.count(DuplicateSet.id)).group_by(
            DuplicateSet.scan_method
        )
    )
    method_dist = {row[0] or "unknown": row[1] for row in result.all()}

    return {
        "total_sets": total_sets,
        "pending_sets": pending_sets,
        "processed_sets": processed_sets,
        "space_reclaimable": space_reclaimable,
        "space_freed": space_freed,
        "total_files": total_files,
        "total_deletions": total_deletions,
        "scan_method_distribution": method_dist,
    }


@router.get("/history")
async def get_deletion_history(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Get deletion history."""
    result = await db.execute(
        select(DeletionHistory)
        .options(selectinload(DeletionHistory.duplicate_file))
        .order_by(DeletionHistory.deleted_at.desc())
        .offset(offset)
        .limit(limit)
    )
    history = result.scalars().all()

    count_result = await db.execute(select(func.count(DeletionHistory.id)))
    total = count_result.scalar() or 0

    return {
        "total": total,
        "items": [
            {
                "id": h.id,
                "duplicate_file_id": h.duplicate_file_id,
                "file_path": h.duplicate_file.file_path if h.duplicate_file else None,
                "file_size": h.duplicate_file.file_size if h.duplicate_file else None,
                "deleted_at": h.deleted_at.isoformat() if h.deleted_at else None,
                "deleted_from_disk": h.deleted_from_disk,
                "plex_refreshed": h.plex_refreshed,
                "deleted_from_arr": h.deleted_from_arr,
                "error": h.error,
            }
            for h in history
        ],
    }
