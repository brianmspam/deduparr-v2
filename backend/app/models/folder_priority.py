from sqlalchemy import Boolean, Column, Integer, String
from app.core.database import Base

class FolderPriority(Base):
    __tablename__ = "folder_priority"

    id = Column(Integer, primary_key=True, index=True)
    path = Column(String, unique=True, index=True, nullable=False)
    # "high", "medium", "low"
    priority = Column(String, nullable=False, default="medium")
    enabled = Column(Boolean, nullable=False, default=True)
    file_count = Column(Integer, nullable=False, default=0)
