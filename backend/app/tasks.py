from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from celery import Task, chain
from PIL import Image, ImageDraw
from sqlalchemy import func, select

from app.celery_app import celery_app
from app.config import settings
from app.database import SessionLocal
from app.models import MediaTask
from app.storage import upload_file_to_storage


class TransientProcessingError(Exception):
    pass


class BaseMediaTask(Task):
    autoretry_for = (TransientProcessingError,)
    retry_backoff = True
    retry_backoff_max = 60
    retry_jitter = True
    max_retries = 5

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        ctx = args[0] if args else {}
        media_task_id = ctx.get("media_task_id")
        if media_task_id:
            update_media_row(
                media_task_id=media_task_id,
                status="failed",
                error_message=str(exc),
            )
        super().on_failure(exc, task_id, args, kwargs, einfo)


def run_media_pipeline(media_task_id: str, input_path: str):
    initial_ctx = {"media_task_id": media_task_id, "input_path": input_path}
    return chain(
        validate_media.s(),
        generate_thumbnail.s(),
        convert_resolutions.s(),
        apply_watermark.s(),
        upload_outputs.s(),
        finalize_success.s(),
    ).apply_async(args=[initial_ctx])


def update_media_row(
    media_task_id: str,
    status: str | None = None,
    progress: int | None = None,
    outputs: dict[str, Any] | None = None,
    error_message: str | None = None,
    thumbnail_path: str | None = None,
):
    db = SessionLocal()
    try:
        row = db.get(MediaTask, UUID(media_task_id))
        if not row:
            return
        if status is not None:
            row.status = status
        if progress is not None:
            row.progress = progress
        if outputs is not None:
            row.outputs = outputs
        if error_message is not None:
            row.error_message = error_message
        if thumbnail_path is not None:
            row.thumbnail_path = thumbnail_path
        db.commit()
    finally:
        db.close()


def _ensure_dirs():
    settings.media_input_dir.mkdir(parents=True, exist_ok=True)
    settings.media_output_dir.mkdir(parents=True, exist_ok=True)
    settings.media_thumb_dir.mkdir(parents=True, exist_ok=True)


def _file_kind(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".jpg", ".jpeg", ".png", ".webp"}:
        return "image"
    if ext in {".mp4", ".mov", ".mkv", ".webm"}:
        return "video"
    raise ValueError(f"Unsupported media format: {ext}")


@celery_app.task(bind=True, base=BaseMediaTask, name="app.tasks.validate_media")
def validate_media(self, ctx: dict[str, Any]):
    _ensure_dirs()
    input_path = Path(ctx["input_path"])
    if not input_path.exists():
        raise ValueError("Uploaded source file does not exist")

    kind = _file_kind(input_path)
    size_bytes = input_path.stat().st_size
    if size_bytes == 0:
        raise ValueError("Uploaded file is empty")

    ctx["kind"] = kind
    ctx["size_bytes"] = size_bytes
    update_media_row(ctx["media_task_id"], status="processing", progress=10)
    self.update_state(state="PROGRESS", meta={"progress": 10, "step": "validate"})
    return ctx


@celery_app.task(bind=True, base=BaseMediaTask, name="app.tasks.generate_thumbnail")
def generate_thumbnail(self, ctx: dict[str, Any]):
    source = Path(ctx["input_path"])
    thumb_path = settings.media_thumb_dir / f"{source.stem}_thumb.jpg"

    if ctx["kind"] == "image":
        with Image.open(source) as img:
            img.thumbnail((320, 320))
            img.convert("RGB").save(thumb_path, "JPEG")
    else:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-ss",
            "00:00:01",
            "-frames:v",
            "1",
            str(thumb_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise TransientProcessingError("Failed to generate video thumbnail")

    ctx["thumbnail_path"] = str(thumb_path)
    update_media_row(ctx["media_task_id"], progress=25, thumbnail_path=str(thumb_path))
    self.update_state(state="PROGRESS", meta={"progress": 25, "step": "thumbnail"})
    return ctx


@celery_app.task(bind=True, base=BaseMediaTask, name="app.tasks.convert_resolutions")
def convert_resolutions(self, ctx: dict[str, Any]):
    source = Path(ctx["input_path"])
    resolutions = [("1080p", 1920), ("720p", 1280), ("480p", 854)]
    converted: list[dict[str, str]] = []

    for label, width in resolutions:
        out_name = f"{source.stem}_{label}{source.suffix}"
        out_path = settings.media_output_dir / out_name
        if ctx["kind"] == "image":
            with Image.open(source) as img:
                ratio = width / float(img.width)
                height = max(1, int(img.height * ratio))
                resized = img.resize((width, height))
                resized.save(out_path)
        else:
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(source),
                "-vf",
                f"scale={width}:-2",
                "-c:a",
                "copy",
                str(out_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise TransientProcessingError(f"Failed to convert {label}")
        converted.append({"label": label, "path": str(out_path)})

    ctx["converted"] = converted
    update_media_row(ctx["media_task_id"], progress=55)
    self.update_state(state="PROGRESS", meta={"progress": 55, "step": "convert"})
    return ctx


@celery_app.task(bind=True, base=BaseMediaTask, name="app.tasks.apply_watermark")
def apply_watermark(self, ctx: dict[str, Any]):
    watermark_text = "Celery Demo"
    watermarked: list[dict[str, str]] = []

    for item in ctx["converted"]:
        src = Path(item["path"])
        dst = src.with_name(f"{src.stem}_wm{src.suffix}")
        if ctx["kind"] == "image":
            with Image.open(src).convert("RGBA") as img:
                overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
                draw = ImageDraw.Draw(overlay)
                draw.text((20, 20), watermark_text, fill=(255, 255, 255, 160))
                combined = Image.alpha_composite(img, overlay).convert("RGB")
                combined.save(dst)
        else:
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(src),
                "-vf",
                "drawtext=text='Celery Demo':x=20:y=20:fontcolor=white:fontsize=24:box=1:boxcolor=black@0.4",
                str(dst),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise TransientProcessingError("Failed to watermark video")
        watermarked.append({"label": item["label"], "path": str(dst)})

    ctx["watermarked"] = watermarked
    update_media_row(ctx["media_task_id"], progress=75)
    self.update_state(state="PROGRESS", meta={"progress": 75, "step": "watermark"})
    return ctx


@celery_app.task(bind=True, base=BaseMediaTask, name="app.tasks.upload_outputs")
def upload_outputs(self, ctx: dict[str, Any]):
    media_task_id = ctx["media_task_id"]
    uploaded = []
    for item in ctx["watermarked"]:
        path = Path(item["path"])
        object_key = f"{media_task_id}/{path.name}"
        url = upload_file_to_storage(path, object_key)
        uploaded.append({"label": item["label"], "url": url, "path": str(path)})

    thumb_key = f"{media_task_id}/{Path(ctx['thumbnail_path']).name}"
    thumb_url = upload_file_to_storage(Path(ctx["thumbnail_path"]), thumb_key)

    ctx["uploaded"] = uploaded
    ctx["thumbnail_url"] = thumb_url
    update_media_row(ctx["media_task_id"], progress=90)
    self.update_state(state="PROGRESS", meta={"progress": 90, "step": "upload"})
    return ctx


@celery_app.task(bind=True, base=BaseMediaTask, name="app.tasks.finalize_success")
def finalize_success(self, ctx: dict[str, Any]):
    outputs = {
        "thumbnail": ctx["thumbnail_url"],
        "variants": [{"label": x["label"], "url": x["url"]} for x in ctx["uploaded"]],
    }
    update_media_row(
        media_task_id=ctx["media_task_id"],
        status="completed",
        progress=100,
        outputs=outputs,
        error_message=None,
    )
    self.update_state(state="SUCCESS", meta={"progress": 100, "step": "done"})
    return outputs


@celery_app.task(name="app.tasks.cleanup_old_media")
def cleanup_old_media():
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=settings.cleanup_max_age_hours)

    cleaned_files = 0
    for root in [settings.media_input_dir, settings.media_output_dir, settings.media_thumb_dir]:
        root.mkdir(parents=True, exist_ok=True)
        for path in root.glob("*"):
            if not path.is_file():
                continue
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if modified < cutoff:
                path.unlink(missing_ok=True)
                cleaned_files += 1

    return {"cleaned_files": cleaned_files, "cutoff": cutoff.isoformat()}


@celery_app.task(name="app.tasks.generate_daily_report")
def generate_daily_report():
    db = SessionLocal()
    try:
        yesterday = datetime.now(timezone.utc) - timedelta(hours=24)
        stmt = (
            select(MediaTask.status, func.count(MediaTask.id))
            .where(MediaTask.created_at >= yesterday)
            .group_by(MediaTask.status)
        )
        rows = db.execute(stmt).all()
        report = {status: count for status, count in rows}
        return {"window_start": yesterday.isoformat(), "counts": report}
    finally:
        db.close()
