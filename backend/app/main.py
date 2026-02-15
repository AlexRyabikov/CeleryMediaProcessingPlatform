import asyncio
from pathlib import Path
from uuid import UUID

from celery.result import AsyncResult
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import settings
from app.database import Base, SessionLocal, engine, get_db
from app.models import MediaTask
from app.schemas import TaskResponse, UploadResponse
from app.tasks import run_media_pipeline

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    settings.media_input_dir.mkdir(parents=True, exist_ok=True)
    settings.media_output_dir.mkdir(parents=True, exist_ok=True)
    settings.media_thumb_dir.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/media/upload", response_model=UploadResponse)
async def upload_media(
    file: UploadFile = File(...),
    user_id: str = Form(...),
    db: Session = Depends(get_db),
):
    active_stmt = select(func.count(MediaTask.id)).where(
        MediaTask.user_id == user_id,
        MediaTask.status.in_(["queued", "processing"]),
    )
    active_count = db.execute(active_stmt).scalar_one()
    if active_count >= settings.max_active_tasks_per_user:
        raise HTTPException(
            status_code=429,
            detail=f"Task quota exceeded. Max active tasks per user: {settings.max_active_tasks_per_user}",
        )

    safe_name = Path(file.filename or "upload.bin").name
    media_row = MediaTask(
        user_id=user_id,
        original_filename=safe_name,
        status="queued",
        progress=0,
        source_path="",
        outputs={},
    )
    db.add(media_row)
    db.flush()

    source_path = settings.media_input_dir / f"{media_row.id}_{safe_name}"
    content = await file.read()
    source_path.write_bytes(content)

    media_row.source_path = str(source_path)
    async_result = run_media_pipeline(str(media_row.id), str(source_path))
    media_row.celery_task_id = async_result.id
    db.commit()
    db.refresh(media_row)

    return UploadResponse(task_id=media_row.id, celery_id=async_result.id, status=media_row.status)


@app.get("/media/tasks/{task_id}", response_model=TaskResponse)
def get_task_status(task_id: UUID, db: Session = Depends(get_db)):
    row = db.get(MediaTask, task_id)
    if not row:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse.model_validate(row)


@app.websocket("/ws/tasks/{task_id}")
async def task_updates(task_id: UUID, websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            db = SessionLocal()
            row = db.get(MediaTask, task_id)
            if not row:
                await websocket.send_json({"error": "Task not found"})
                db.close()
                break

            celery_state = None
            celery_meta = None
            if row.celery_task_id:
                result = AsyncResult(row.celery_task_id, app=celery_app)
                celery_state = result.state
                celery_meta = result.info if isinstance(result.info, dict) else None

            payload = {
                "task_id": str(row.id),
                "status": row.status,
                "progress": row.progress,
                "error_message": row.error_message,
                "outputs": row.outputs,
                "celery": {"state": celery_state, "meta": celery_meta},
            }
            await websocket.send_json(payload)
            db.close()

            if row.status in {"completed", "failed"}:
                break

            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return
