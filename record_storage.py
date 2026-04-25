from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import uuid


@dataclass
class StoredFile:
    original_filename: str
    stored_filename: str
    absolute_path: str
    relative_path: str
    content_type: str
    size_bytes: int


class LocalRecordStorage:
    def __init__(self, base_dir: str | None = None):
        default_dir = Path(__file__).resolve().parent / "uploads"
        self.base_dir = Path(base_dir or os.getenv("RECORD_UPLOAD_DIR", str(default_dir))).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_upload(self, upload_file, owner_user_id: int, profile_id: int) -> StoredFile:
        original_name = upload_file.filename or "record"
        extension = Path(original_name).suffix
        stored_name = f"{owner_user_id}_{profile_id}_{uuid.uuid4().hex}{extension}"

        owner_dir = self.base_dir / str(owner_user_id) / str(profile_id)
        owner_dir.mkdir(parents=True, exist_ok=True)

        destination = owner_dir / stored_name
        with destination.open("wb") as out_file:
            shutil.copyfileobj(upload_file.file, out_file)

        size = destination.stat().st_size
        return StoredFile(
            original_filename=original_name,
            stored_filename=stored_name,
            absolute_path=str(destination),
            relative_path=str(destination.relative_to(self.base_dir)).replace("\\", "/"),
            content_type=(upload_file.content_type or "application/octet-stream"),
            size_bytes=size,
        )


class GCSRecordStorage:
    def __init__(self, bucket_name: str, prefix: str | None = None):
        from google.cloud import storage

        self.bucket_name = bucket_name
        self.prefix = (prefix or os.getenv("GCS_UPLOAD_PREFIX", "uploads")).strip("/")
        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket_name)

    def save_upload(self, upload_file, owner_user_id: int, profile_id: int) -> StoredFile:
        original_name = upload_file.filename or "record"
        extension = Path(original_name).suffix
        stored_name = f"{owner_user_id}_{profile_id}_{uuid.uuid4().hex}{extension}"
        blob_key = f"{self.prefix}/{owner_user_id}/{profile_id}/{stored_name}"
        blob = self._bucket.blob(blob_key)

        file_obj = upload_file.file
        file_obj.seek(0, os.SEEK_END)
        size = file_obj.tell()
        file_obj.seek(0)

        content_type = upload_file.content_type or "application/octet-stream"
        blob.upload_from_file(file_obj, content_type=content_type)

        return StoredFile(
            original_filename=original_name,
            stored_filename=stored_name,
            absolute_path=f"gs://{self.bucket_name}/{blob_key}",
            relative_path=blob_key,
            content_type=content_type,
            size_bytes=size,
        )


def build_record_storage():
    backend = os.getenv("RECORD_STORAGE_BACKEND", "local").strip().lower()
    gcs_bucket = os.getenv("GCS_BUCKET_NAME", "").strip()

    if backend == "gcs" or gcs_bucket:
        if not gcs_bucket:
            raise RuntimeError("GCS_BUCKET_NAME must be set when using GCS record storage")
        return GCSRecordStorage(bucket_name=gcs_bucket)

    return LocalRecordStorage()
