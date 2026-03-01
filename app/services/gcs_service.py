import logging
from google.cloud import storage

from app.core.config import settings

logger = logging.getLogger(__name__)


class GCSService:
    def __init__(self):
        self.client = storage.Client(project=settings.PROJECT_ID)

    def upload_bytes(self, data: bytes, object_name: str, content_type: str = "application/octet-stream") -> str:
        if not settings.GCS_BUCKET:
            raise ValueError("GCS_BUCKET env var is required.")

        bucket = self.client.bucket(settings.GCS_BUCKET)
        blob = bucket.blob(object_name)
        blob.upload_from_string(data, content_type=content_type)
        return f"gs://{settings.GCS_BUCKET}/{object_name}"

    def download_bytes(self, gcs_uri: str) -> bytes:
        if not gcs_uri.startswith("gs://"):
            raise ValueError("gcs_uri must start with gs://")
        _, path = gcs_uri.split("gs://", 1)
        bucket_name, blob_name = path.split("/", 1)
        blob = self.client.bucket(bucket_name).blob(blob_name)
        return blob.download_as_bytes()