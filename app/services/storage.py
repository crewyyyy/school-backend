from pathlib import Path
from uuid import uuid4

import boto3
from fastapi import UploadFile

from app.core.config import get_settings


class StorageService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.backend = self.settings.storage_backend.lower()

        if self.backend == "s3":
            self.s3_client = boto3.client(
                "s3",
                endpoint_url=self.settings.s3_endpoint,
                aws_access_key_id=self.settings.s3_access_key,
                aws_secret_access_key=self.settings.s3_secret_key,
                region_name=self.settings.s3_region,
            )
        else:
            self.s3_client = None
            self.settings.media_path.mkdir(parents=True, exist_ok=True)

    async def save_upload(self, upload_file: UploadFile, prefix: str) -> str:
        suffix = Path(upload_file.filename or "file").suffix or ".bin"
        object_key = f"{prefix}/{uuid4().hex}{suffix}"
        content = await upload_file.read()
        content_type = upload_file.content_type or "application/octet-stream"

        if self.backend == "s3":
            return self._save_s3(object_key=object_key, content=content, content_type=content_type)

        return self._save_local(object_key=object_key, content=content)

    def _save_local(self, object_key: str, content: bytes) -> str:
        path = self.settings.media_path / object_key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        key_url = object_key.replace("\\", "/")
        return f"{self.settings.media_base_url.rstrip('/')}/{key_url}"

    def _save_s3(self, object_key: str, content: bytes, content_type: str) -> str:
        assert self.s3_client is not None
        self.s3_client.put_object(
            Bucket=self.settings.s3_bucket,
            Key=object_key,
            Body=content,
            ContentType=content_type,
        )
        if self.settings.s3_public_base_url:
            return f"{self.settings.s3_public_base_url.rstrip('/')}/{object_key}"
        endpoint = self.settings.s3_endpoint.rstrip("/")
        return f"{endpoint}/{self.settings.s3_bucket}/{object_key}"

