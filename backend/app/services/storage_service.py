"""File storage abstraction: local filesystem (default) or S3-compatible.

Keys are storage-relative paths like ``media/<asset_id>/original/<file>``. The
backend is chosen from settings; S3 is used only when explicitly configured.
"""

from __future__ import annotations

from pathlib import Path

from app.config import settings


class LocalStorage:
    backend = "local"

    def __init__(self, base_dir: str):
        self.base = Path(base_dir)

    def save(self, key: str, data: bytes) -> str:
        path = self.base / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def read(self, key: str) -> bytes:
        return (self.base / key).read_bytes()

    def exists(self, key: str) -> bool:
        return (self.base / key).exists()

    def delete(self, key: str) -> None:
        path = self.base / key
        if path.exists():
            path.unlink()


class S3Storage:
    backend = "s3"

    def __init__(self):
        import boto3

        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url or None,
            aws_access_key_id=settings.s3_access_key_id or None,
            aws_secret_access_key=settings.s3_secret_access_key or None,
            region_name=settings.s3_region,
        )
        self.bucket = settings.s3_bucket

    def save(self, key: str, data: bytes) -> str:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        return key

    def read(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:  # noqa: BLE001
            return False

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


def get_storage():
    if settings.storage_backend == "s3" and settings.s3_bucket:
        return S3Storage()
    return LocalStorage(settings.storage_local_dir)
