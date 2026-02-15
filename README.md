# Celery Media Processing Platform

Production-ready demo showing how to build asynchronous media processing with `FastAPI + Celery + Redis + Postgres + React + Docker`.

## Problem

User media processing (validation, conversion, thumbnails, watermarking, upload) is expensive and blocks HTTP requests.

## Solution

FastAPI receives uploads and returns immediately, while Celery workers process media in the background and stream progress updates through WebSocket.

## What This Demo Shows

- Async task processing with Celery + Redis broker/result backend
- Real-time progress tracking via WebSocket
- Celery task `chain` for multi-step processing
- Retry logic with exponential backoff for transient failures
- Per-user rate limiting (active task quotas)
- Periodic tasks (cleanup + daily report)
- Object storage upload (MinIO/S3-compatible via boto3)
- Monitoring with Flower

## Architecture

```text
[React UI] -> [FastAPI] -> [Celery Worker] -> [Redis]
     |            |              |             |
     |            v              v             v
     |        [Postgres]   [MinIO/S3]   [Celery Results]
     |
     +------ WebSocket progress updates ------>
```

## Processing Flow

1. User uploads media (`/media/upload`) and gets `task_id` instantly
2. Celery pipeline runs in background:
   - validate file
   - generate thumbnail
   - convert to multiple resolutions
   - apply watermark
   - upload outputs to object storage
3. Frontend receives progress updates through WebSocket (`/ws/tasks/{task_id}`)
4. User sees final output URLs when task is complete

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

Services:

- Frontend: `http://localhost:${FRONTEND_PORT}`
- API docs: `http://localhost:${API_PORT}/docs`
- Flower: `http://localhost:${FLOWER_PORT}`

Optional S3/MinIO profile:

```bash
docker compose --profile s3 up --build
```

MinIO console (when profile enabled): `http://localhost:${MINIO_CONSOLE_PORT}`

## Env-Driven Ports

All published ports are configured from `.env`:

- `API_PORT`, `FRONTEND_PORT`, `FLOWER_PORT`
- `POSTGRES_PORT`, `REDIS_PORT`
- `MINIO_API_PORT`, `MINIO_CONSOLE_PORT` (optional S3 profile)

Container-side ports are also configurable via:

- `API_INTERNAL_PORT`, `FRONTEND_INTERNAL_PORT`, `FLOWER_INTERNAL_PORT`, `MINIO_CONSOLE_INTERNAL_PORT`

## Key API Endpoints

- `POST /media/upload` - upload media and enqueue processing
- `GET /media/tasks/{task_id}` - fetch task status and result metadata
- `WS /ws/tasks/{task_id}` - real-time task updates

## Stack

- Backend: `FastAPI`, `SQLAlchemy`, `Celery`, `Redis`, `Postgres`
- Worker media ops: `Pillow`, `ffmpeg`
- Frontend: `React` + `Vite`
- Infra: `Docker Compose`, `MinIO`, `Flower`

## Notes

- This is a demo architecture intended for portfolio and interview walkthroughs.
- For production: add auth, antivirus scanning, robust tenancy limits, signed URLs, and stronger observability (metrics/tracing).
- For remote deploys, do not use `localhost` in `VITE_API_BASE_URL` unless browser and API run on the same machine.
- If `VITE_API_BASE_URL` is empty, frontend uses `window.location.hostname` + `API_PORT` automatically.
