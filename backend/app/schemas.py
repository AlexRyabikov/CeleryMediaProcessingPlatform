from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class UploadResponse(BaseModel):
    task_id: UUID
    celery_id: str
    status: str


class TaskResponse(BaseModel):
    id: UUID
    user_id: str
    original_filename: str
    status: str
    progress: int
    celery_task_id: str | None
    outputs: dict[str, Any]
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
