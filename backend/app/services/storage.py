import os
import boto3
import asyncio
import json
from datetime import datetime, timedelta
from google.cloud import storage
from botocore.client import Config


class StorageProvider:
    def __init__(self, use_gcs=False):
        self.use_gcs = use_gcs
        self._s3_session_client = None
        self._conv_bucket_name = os.getenv("CONVERSATION_SESSIONS_BUCKET", "ivdrive-conversation-sessions-dev")

        if self.use_gcs:
            # GCS (Production/Testing)
            self.bucket_name = os.getenv("GCS_BUCKET", "ivdrive-data-exchange")
            self.client = storage.Client()
            self.bucket = self.client.bucket(self.bucket_name)
        else:
            # S3 Compatible (MinIO, AWS S3, Rustfs, etc.)
            self.bucket_name = os.getenv("S3_BUCKET", "ivdrive-data-extract")
            self.s3_endpoint = os.getenv("S3_ENDPOINT", "https://s3.m7xlab.top")
            self.access_key = os.getenv("S3_ACCESS_KEY", "")
            self.secret_key = os.getenv("S3_SECRET_KEY", "")
            self.use_s3 = os.getenv("USE_S3_STORAGE", "false").lower() == "true"

            if self.use_s3:
                self.client = boto3.client(
                    "s3",
                    endpoint_url=self.s3_endpoint,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
                    region_name="us-east-1",
                )
                # Lazy-init separate session client for conversation bucket
                self._s3_session_client = None

    @property
    def s3_session_client(self):
        """Lazily-created S3 client with conversation bucket credentials."""
        if self._s3_session_client is None:
            self._s3_session_client = boto3.client(
                "s3",
                endpoint_url=self.s3_endpoint,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
                region_name="us-east-1",
            )
        return self._s3_session_client

    async def upload_file(self, file_path: str, destination_blob_name: str):
        if self.use_gcs:
            blob = self.bucket.blob(destination_blob_name)
            await asyncio.to_thread(blob.upload_from_filename, file_path)
        elif getattr(self, "use_s3", False):

            def _upload():
                with open(file_path, "rb") as f:
                    self.client.put_object(Bucket=self.bucket_name, Key=destination_blob_name, Body=f)

            await asyncio.to_thread(_upload)
        else:
            raise Exception("No storage provider configured (USE_GCS_STORAGE and USE_S3_STORAGE are both false)")

    async def upload_content(self, content: str, destination_blob_name: str, bucket_name: str | None = None) -> bool:
        """Upload in-memory string content to S3. Used for chat session JSON logs."""
        if self.use_gcs:
            blob = self.bucket.bucket if hasattr(self.bucket, "bucket") else self.client.bucket(bucket_name or self.bucket_name)
            blob = blob.blob(destination_blob_name)
            await asyncio.to_thread(blob.upload_from_string, content)
            return True
        elif getattr(self, "use_s3", False):
            target_bucket = bucket_name or self.bucket_name
            s3_client = self.s3_session_client if target_bucket == self._conv_bucket_name else self.client

            def _upload():
                s3_client.put_object(Bucket=target_bucket, Key=destination_blob_name, Body=content.encode("utf-8"))

            await asyncio.to_thread(_upload)
            return True
        else:
            return False

    async def upload_chat_session(self, session_id: str, user_id: str, messages: list[dict]) -> bool:
        """Upload a complete chat session as JSON to S3 conversation bucket."""
        session_log = {
            "session_id": session_id,
            "user_id": user_id,
            "messages": messages,
            "uploaded_at": datetime.utcnow().isoformat() + "Z",
        }
        date_prefix = datetime.utcnow().strftime("%Y-%m")
        blob_name = f"{date_prefix}/{session_id}.json"
        try:
            return await self.upload_content(json.dumps(session_log, ensure_ascii=False, indent=2), blob_name, self._conv_bucket_name)
        except Exception as e:
            import logging
            logging.warning(f"[storage] Failed to upload chat session {session_id}: {e}")
            return False

    def generate_download_url(self, blob_name: str, expiration=timedelta(hours=24)) -> str:
        if self.use_gcs:
            blob = self.bucket.blob(blob_name)
            url = blob.generate_signed_url(version="v4", expiration=expiration, method="GET")
            return url
        elif getattr(self, "use_s3", False):
            url = self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": blob_name},
                ExpiresIn=int(expiration.total_seconds()),
            )
            return url
        else:
            raise Exception("No storage provider configured (USE_GCS_STORAGE and USE_S3_STORAGE are both false)")

    async def delete_file(self, blob_name: str):
        if self.use_gcs:
            blob = self.bucket.blob(blob_name)

            def _delete_gcs():
                if blob.exists():
                    blob.delete()

            await asyncio.to_thread(_delete_gcs)
        elif getattr(self, "use_s3", False):
            await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket_name, Key=blob_name)
        else:
            raise Exception("No storage provider configured (USE_GCS_STORAGE and USE_S3_STORAGE are both false)")
