from celery import Celery

from app.config import settings


celery_app = Celery(
    "media_platform",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    timezone="UTC",
    beat_schedule={
        "cleanup-old-media-every-hour": {
            "task": "app.tasks.cleanup_old_media",
            "schedule": 3600.0,
        },
        "generate-daily-report": {
            "task": "app.tasks.generate_daily_report",
            "schedule": 86400.0,
        },
    },
)
