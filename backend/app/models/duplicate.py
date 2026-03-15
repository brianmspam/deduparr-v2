import enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base, utc_now


class DuplicateStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROCESSED = "processed"


class MediaType(str, enum.Enum):
    MOVIE = "movie"
    EPISODE = "episode"


class DuplicateSet(Base):
    __tablename__ = "duplicate_sets"

    id = Column(Integer, primary_key=True, index=True)
    plex_item_id = Column(String(255), nullable=True, index=True)
    title = Column(String(500), nullable=False)
    media_type = Column(SQLEnum(MediaType), nullable=False)
    found_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    status = Column(
        SQLEnum(DuplicateStatus),
        default=DuplicateStatus.PENDING,
        nullable=False,
        index=True,
    )
    space_to_reclaim = Column(BigInteger, default=0)
    scan_method = Column(String(50), nullable=True)

    files = relationship(
        "DuplicateFile", back_populates="duplicate_set", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_status_found_at", "status", "found_at"),)


class DuplicateFile(Base):
    __tablename__ = "duplicate_files"

    id = Column(Integer, primary_key=True, index=True)
    set_id = Column(
        Integer,
        ForeignKey("duplicate_sets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_path = Column(Text, nullable=False, index=True)
    file_size = Column(BigInteger, nullable=False)
    score = Column(Integer, default=0, nullable=False)
    keep = Column(Boolean, default=False, nullable=False)
    inode = Column(BigInteger, nullable=True, index=True)
    is_hardlink = Column(Boolean, default=False, nullable=False)
    file_metadata = Column(Text, nullable=True)

    duplicate_set = relationship("DuplicateSet", back_populates="files")
    deletion_history = relationship(
        "DeletionHistory", back_populates="duplicate_file", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("idx_set_file", "set_id", "file_path"),)
