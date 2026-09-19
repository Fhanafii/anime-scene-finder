from __future__ import annotations

import os
from pathlib import Path


class ObjectStore:
    def __init__(self) -> None:
        self.endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9002")
        self.access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
        self.secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
        self.bucket = os.getenv("MINIO_BUCKET", "anime-keyframes")

    def upload(self, path: Path, object_key: str) -> str:
        from minio import Minio

        client = Minio(self.endpoint, access_key=self.access_key, secret_key=self.secret_key, secure=False)
        if not client.bucket_exists(self.bucket):
            client.make_bucket(self.bucket)
        client.fput_object(self.bucket, object_key, str(path), content_type="image/jpeg")
        return object_key

    def read(self, object_key: str) -> bytes:
        from minio import Minio

        client = Minio(self.endpoint, access_key=self.access_key, secret_key=self.secret_key, secure=False)
        response = client.get_object(self.bucket, object_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()
