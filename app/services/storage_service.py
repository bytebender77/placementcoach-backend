"""
Storage service — S3 in production, local filesystem in development.
Set STORAGE_BACKEND=local in .env to skip AWS credentials during dev.
"""

import os
import uuid
import shutil
from pathlib import Path

from app.core.config import settings


# ── Local filesystem backend ────────────────────────────────────────────────

LOCAL_STORAGE_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"


def _ensure_local_dir(key: str) -> Path:
    path = LOCAL_STORAGE_DIR / key
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _local_upload(file_bytes: bytes, user_id: str, filename: str) -> str:
    key = f"resumes/{user_id}/{uuid.uuid4()}/{filename}"
    path = _ensure_local_dir(key)
    path.write_bytes(file_bytes)
    return key


def _local_presigned_url(s3_key: str, expires_in: int = 3600) -> str:
    # In dev, just return a file path reference — frontend can't use this
    # but the backend never actually needs the URL for core logic
    return f"/uploads/{s3_key}"


def _local_delete(s3_key: str):
    path = LOCAL_STORAGE_DIR / s3_key
    if path.exists():
        path.unlink()


# ── S3 backend ──────────────────────────────────────────────────────────────

def _s3_client():
    import boto3
    return boto3.client(
        "s3",
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_REGION,
    )


def _s3_upload(file_bytes: bytes, user_id: str, filename: str) -> str:
    key = f"resumes/{user_id}/{uuid.uuid4()}/{filename}"
    _s3_client().put_object(
        Bucket=settings.S3_BUCKET_NAME,
        Key=key,
        Body=file_bytes,
        ContentType="application/pdf",
    )
    return key


def _s3_presigned_url(s3_key: str, expires_in: int = 3600) -> str:
    from botocore.exceptions import ClientError
    try:
        url = _s3_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.S3_BUCKET_NAME, "Key": s3_key},
            ExpiresIn=expires_in,
        )
        return url
    except ClientError as e:
        raise RuntimeError(f"Could not generate presigned URL: {e}")


def _s3_delete(s3_key: str):
    _s3_client().delete_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key)


# ── Public API (routes based on STORAGE_BACKEND setting) ────────────────────

_use_local = getattr(settings, "STORAGE_BACKEND", "s3").lower() == "local"


def upload_resume(file_bytes: bytes, user_id: str, filename: str) -> str:
    if _use_local:
        return _local_upload(file_bytes, user_id, filename)
    return _s3_upload(file_bytes, user_id, filename)


def get_presigned_url(s3_key: str, expires_in: int = 3600) -> str:
    if _use_local:
        return _local_presigned_url(s3_key, expires_in)
    return _s3_presigned_url(s3_key, expires_in)


def delete_resume(s3_key: str):
    if _use_local:
        return _local_delete(s3_key)
    return _s3_delete(s3_key)
