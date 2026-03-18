"""Scoring endpoints — CRUD for custom scoring rules."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.models.scoring_rule import ScoringRule

router = APIRouter()
logger = logging.getLogger(__name__)


class ScoringRuleCreate(BaseModel):
    name: str
    pattern: str
    score_modifier: int = 0
    enabled: bool = True


class ScoringRuleUpdate(BaseModel):
    name: str | None = None
    pattern: str | None = None
    score_modifier: int | None = None
    enabled: bool | None = None


@router.get("/rules")
async def get_scoring_rules(db: AsyncSession = Depends(get_db)):
    """Get all scoring rules."""
    result = await db.execute(select(ScoringRule).order_by(ScoringRule.created_at.desc()))
    rules = result.scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "pattern": r.pattern,
            "score_modifier": r.score_modifier,
            "enabled": r.enabled,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rules
    ]


@router.post("/rules")
async def create_scoring_rule(
    request: ScoringRuleCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a custom scoring rule."""
    rule = ScoringRule(
        name=request.name,
        pattern=request.pattern,
        score_modifier=request.score_modifier,
        enabled=request.enabled,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return {
        "id": rule.id,
        "name": rule.name,
        "pattern": rule.pattern,
        "score_modifier": rule.score_modifier,
        "enabled": rule.enabled,
    }


@router.put("/rules/{rule_id}")
async def update_scoring_rule(
    rule_id: int,
    request: ScoringRuleUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a scoring rule."""
    result = await db.execute(select(ScoringRule).where(ScoringRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    if request.name is not None:
        rule.name = request.name
    if request.pattern is not None:
        rule.pattern = request.pattern
    if request.score_modifier is not None:
        rule.score_modifier = request.score_modifier
    if request.enabled is not None:
        rule.enabled = request.enabled

    await db.commit()
    return {
        "id": rule.id,
        "name": rule.name,
        "pattern": rule.pattern,
        "score_modifier": rule.score_modifier,
        "enabled": rule.enabled,
    }


@router.delete("/rules/{rule_id}")
async def delete_scoring_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a scoring rule."""
    result = await db.execute(select(ScoringRule).where(ScoringRule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    await db.delete(rule)
    await db.commit()
    return {"status": "deleted", "id": rule_id}

class FolderPriorityOut(BaseModel):
    id: int
    path: str
    priority: str
    enabled: bool

    class Config:
        orm_mode = True

class FolderPriorityUpdate(BaseModel):
    priority: str | None = None
    enabled: bool | None = None

@router.get("/folder-priority", response_model=list[FolderPriorityOut])
async def list_folder_priorities(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FolderPriority).order_by(FolderPriority.path))
    return result.scalars().all()

@router.patch("/folder-priority/{folder_id}", response_model=FolderPriorityOut)
async def update_folder_priority(
    folder_id: int,
    payload: FolderPriorityUpdate,
    db: AsyncSession = Depends(get_db),
):
    fp = await db.get(FolderPriority, folder_id)
    if not fp:
        raise HTTPException(status_code=404, detail="Folder not found")

    if payload.priority is not None:
        if payload.priority not in {"high", "medium", "low"}:
            raise HTTPException(status_code=400, detail="Invalid priority")
        fp.priority = payload.priority
    if payload.enabled is not None:
        fp.enabled = payload.enabled

    await db.commit()
    await db.refresh(fp)
    return fp