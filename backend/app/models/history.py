from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import relationship

from app.core.database import Base, utc_now


class DeletionHistory(Base):
    __tablename__ = "deletion_history"

    id = Column(Integer, primary_key=True, index=True)
    duplicate_file_id = Column(
        Integer,
        ForeignKey("duplicate_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    deleted_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    deleted_from_disk = Column(Boolean, default=False, nullable=False)
    plex_refreshed = Column(Boolean, default=False, nullable=False)
    deleted_from_arr = Column(Boolean, default=False, nullable=False)
    error = Column(Text, nullable=True)
    arr_type = Column(Text, nullable=True)

    duplicate_file = relationship("DuplicateFile", back_populates="deletion_history")

    __table_args__ = (Index("idx_deleted_at_desc", "deleted_at"),)
