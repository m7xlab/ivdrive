import os
import boto3
import asyncio
from datetime import timedelta
from google.cloud import storage
from botocore.client import Config

class StorageProvider:
    def __init__(self, use_gcs=False):
        self.use_gcs = use_gcs
        if self.use_gcs:
            # GCS (Production/Testing)
            # Service account path should be defined in env var GOOGLE_APPLICATION_CREDENTIALS
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
                    's3',
                    endpoint_url=self.s3_endpoint,
                    aws_access_key_id=self.access_key,
                    aws_secret_access_key=self.secret_key,
                    config=Config(signature_version='s3v4', s3={'addressing_style': 'path'}),
                    region_name='us-east-1'
                )

    async def upload_file(self, file_path: str, destination_blob_name: str):
        if self.use_gcs:
            blob = self.bucket.blob(destination_blob_name)
            await asyncio.to_thread(blob.upload_from_filename, file_path)
        elif getattr(self, 'use_s3', False):
            def _upload():
                with open(file_path, "rb") as f:
                    self.client.put_object(Bucket=self.bucket_name, Key=destination_blob_name, Body=f)
            await asyncio.to_thread(_upload)
        else:
            raise Exception("No storage provider configured (USE_GCS_STORAGE and USE_S3_STORAGE are both false)")

    def generate_download_url(self, blob_name: str, expiration=timedelta(hours=24)) -> str:
        if self.use_gcs:
            blob = self.bucket.blob(blob_name)
            url = blob.generate_signed_url(
                version="v4",
                expiration=expiration,
                method="GET"
            )
            return url
        elif getattr(self, 'use_s3', False):
            url = self.client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': blob_name},
                ExpiresIn=int(expiration.total_seconds())
            )
            return url
        else:
            raise Exception("No storage provider configured (USE_GCS_STORAGE and USE_S3_STORAGE are both false)")

    def delete_file(self, blob_name: str):
        if self.use_gcs:
            blob = self.bucket.blob(blob_name)
            if blob.exists():
                blob.delete()
        elif getattr(self, 'use_s3', False):
            self.client.delete_object(Bucket=self.bucket_name, Key=blob_name)
