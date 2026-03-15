from sqlalchemy import Boolean, Column, DateTime, Index, Integer, String, Text

from app.core.database import Base, utc_now


class ScoringRule(Base):
    __tablename__ = "scoring_rules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    pattern = Column(Text, nullable=False)
    score_modifier = Column(Integer, default=0, nullable=False)
    enabled = Column(Boolean, default=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (Index("idx_enabled", "enabled"),)
