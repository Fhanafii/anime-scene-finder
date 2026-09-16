from __future__ import annotations

import os
from pathlib import Path


class ObjectStore:
    def __init__(self) -> None:
        self.endpoint = os.environ["MINIO_ENDPOINT"]
        self.access_key = os.environ["MINIO_ACCESS_KEY"]
        self.secret_key = os.environ["MINIO_SECRET_KEY"]
        self.bucket = os.environ["MINIO_BUCKET"]

    def upload(self, path: Path, object_key: str) -> str:
        from minio import Minio

        client = Minio(self.endpoint, access_key=self.access_key, secret_key=self.secret_key, secure=False)
        if not client.bucket_exists(self.bucket):
            client.make_bucket(self.bucket)
        client.fput_object(self.bucket, object_key, str(path), content_type="image/jpeg")
        return object_key
