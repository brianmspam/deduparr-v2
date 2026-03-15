"""
Scoring engine — ports the Phase 1 algorithm from plex_dedup.py exactly.
Higher score = better file = KEEP.
"""

import logging
import re
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scoring_rule import ScoringRule

logger = logging.getLogger(__name__)

# ─── Scoring weights (must match plex_dedup.py exactly) ───────────────────────

CODEC_SCORES: dict[str, int] = {
    "hevc": 50, "h265": 50, "h.265": 50, "x265": 50,
    "h264": 30, "h.264": 30, "x264": 30, "avc": 30,
    "av1": 55,
}
CODEC_DEFAULT = 10

CONTAINER_SCORES: dict[str, int] = {
    "mkv": 40,
    "mp4": 20,
    "avi": 5,
}
CONTAINER_DEFAULT = 10

RESOLUTION_TIERS: list[tuple[int, int]] = [
    (7_000_000, 50),   # 4K
    (1_800_000, 35),   # 1080p
    (800_000,   20),   # 720p
    (0,          5),   # SD
]

SIZE_SCORE_MAX = 30


class ScoringEngine:
    def __init__(self, db: AsyncSession | None = None):
        self.db = db
        self._custom_rules: list[dict[str, Any]] | None = None

    async def _load_custom_rules(self) -> list[dict[str, Any]]:
        if self._custom_rules is not None:
            return self._custom_rules
        if self.db is None:
            self._custom_rules = []
            return self._custom_rules
        result = await self.db.execute(
            select(ScoringRule).where(ScoringRule.enabled == True)  # noqa: E712
        )
        rules = result.scalars().all()
        self._custom_rules = [
            {"pattern": r.pattern, "score_modifier": r.score_modifier, "name": r.name}
            for r in rules
        ]
        return self._custom_rules

    @staticmethod
    def compute_codec_score(codec: str) -> int:
        return CODEC_SCORES.get(codec.lower().strip(), CODEC_DEFAULT)

    @staticmethod
    def compute_container_score(container: str) -> int:
        return CONTAINER_SCORES.get(container.lower().strip(), CONTAINER_DEFAULT)

    @staticmethod
    def compute_resolution_score(width: int, height: int) -> int:
        pixels = (width or 0) * (height or 0)
        for threshold, score in RESOLUTION_TIERS:
            if pixels >= threshold:
                return score
        return 5

    @staticmethod
    def compute_size_score(
        file_size: int, min_size: int, max_size: int
    ) -> int:
        if max_size == min_size:
            return SIZE_SCORE_MAX // 2
        return int(SIZE_SCORE_MAX * (1.0 - (file_size - min_size) / (max_size - min_size)))

    def _apply_custom_rules(self, file_path: str, rules: list[dict[str, Any]]) -> int:
        modifier = 0
        for rule in rules:
            try:
                if re.search(rule["pattern"], file_path, re.IGNORECASE):
                    modifier += rule["score_modifier"]
            except re.error:
                logger.warning(f"Invalid regex pattern in rule '{rule['name']}': {rule['pattern']}")
        return modifier

    async def score_file(
        self,
        codec: str,
        container: str,
        width: int,
        height: int,
        file_size: int,
        min_size: int,
        max_size: int,
        file_path: str = "",
    ) -> dict[str, int]:
        codec_score = self.compute_codec_score(codec)
        container_score = self.compute_container_score(container)
        resolution_score = self.compute_resolution_score(width, height)
        size_score = self.compute_size_score(file_size, min_size, max_size)

        custom_modifier = 0
        if file_path:
            rules = await self._load_custom_rules()
            custom_modifier = self._apply_custom_rules(file_path, rules)

        total = codec_score + container_score + resolution_score + size_score + custom_modifier

        return {
            "codec_score": codec_score,
            "container_score": container_score,
            "resolution_score": resolution_score,
            "size_score": size_score,
            "custom_modifier": custom_modifier,
            "total_score": total,
        }

    async def rank_group(self, files: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Score and rank a group of duplicate files.
        Each file dict must have: codec, container, width, height, file_size, file_path
        Returns the files with score breakdown, rank, and action.
        """
        if not files:
            return []

        sizes = [f.get("file_size", 0) or 0 for f in files]
        min_size = min(sizes) if sizes else 0
        max_size = max(sizes) if sizes else 0

        for f in files:
            breakdown = await self.score_file(
                codec=f.get("codec", "") or "",
                container=f.get("container", "") or "",
                width=f.get("width", 0) or 0,
                height=f.get("height", 0) or 0,
                file_size=f.get("file_size", 0) or 0,
                min_size=min_size,
                max_size=max_size,
                file_path=f.get("file_path", ""),
            )
            f.update(breakdown)

        # Sort: highest score first, then smallest file, then newest media_item_id
        files.sort(
            key=lambda v: (
                -v["total_score"],
                v.get("file_size", 0) or 0,
                -(v.get("media_item_id", 0) or 0),
            )
        )

        for rank, f in enumerate(files, 1):
            f["rank"] = rank
            f["action"] = "KEEP" if rank == 1 else "DELETE"

        return files

    async def rank_all_groups(
        self, rows: list[dict[str, Any]], group_key: str = "metadata_id"
    ) -> list[dict[str, Any]]:
        groups: dict[Any, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[row[group_key]].append(row)

        results: list[dict[str, Any]] = []
        for group_files in groups.values():
            ranked = await self.rank_group(group_files)
            results.extend(ranked)

        return results
