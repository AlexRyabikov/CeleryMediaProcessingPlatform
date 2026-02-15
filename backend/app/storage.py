from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )


def upload_file_to_storage(path: Path, object_key: str) -> str:
    if not settings.s3_enabled:
        return str(path)

    client = get_s3_client()
    try:
        client.upload_file(str(path), settings.s3_bucket, object_key)
        return f"{settings.s3_public_base_url}/{settings.s3_bucket}/{object_key}"
    except (BotoCoreError, ClientError):
        return str(path)
