from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Celery Media Processing Platform"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    database_url: str = "postgresql+psycopg2://postgres:postgres@postgres:5432/media_platform"
    redis_url: str = "redis://redis:6379/0"

    media_root: str = "/tmp/media"
    max_active_tasks_per_user: int = 3
    cleanup_max_age_hours: int = 72

    s3_enabled: bool = True
    s3_endpoint_url: str = "http://minio:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "media"
    s3_region: str = "us-east-1"
    s3_public_base_url: str = "http://localhost:9000"

    @property
    def media_input_dir(self) -> Path:
        return Path(self.media_root) / "input"

    @property
    def media_output_dir(self) -> Path:
        return Path(self.media_root) / "output"

    @property
    def media_thumb_dir(self) -> Path:
        return Path(self.media_root) / "thumb"

    @property
    def cors_origins_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


settings = Settings()
