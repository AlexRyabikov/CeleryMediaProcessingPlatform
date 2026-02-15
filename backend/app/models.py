import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MediaTask(Base):
    __tablename__ = "media_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(120), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    celery_task_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    source_path: Mapped[str] = mapped_column(Text)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    outputs: Mapped[dict] = mapped_column(JSONB, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
