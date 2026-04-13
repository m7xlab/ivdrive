import os
import boto3
import asyncio
from datetime import timedelta
from google.cloud import storage

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
            # Rustfs (Local S3 compatible)
            self.bucket_name = os.getenv("S3_BUCKET", "ivdrive-data-extract")
            self.s3_endpoint = os.getenv("S3_ENDPOINT", "https://s3.m7xlab.top")
            self.access_key = os.getenv("S3_ACCESS_KEY", "")
            self.secret_key = os.getenv("S3_SECRET_KEY", "")
            
            self.client = boto3.client(
                's3',
                endpoint_url=self.s3_endpoint,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key
            )

    async def upload_file(self, file_path: str, destination_blob_name: str):
        if self.use_gcs:
            blob = self.bucket.blob(destination_blob_name)
            await asyncio.to_thread(blob.upload_from_filename, file_path)
        else:
            def _upload():
                with open(file_path, "rb") as f:
                    self.client.put_object(Bucket=self.bucket_name, Key=destination_blob_name, Body=f)
            await asyncio.to_thread(_upload)

    def generate_download_url(self, blob_name: str, expiration=timedelta(hours=24)) -> str:
        if self.use_gcs:
            blob = self.bucket.blob(blob_name)
            url = blob.generate_signed_url(
                version="v4",
                expiration=expiration,
                method="GET"
            )
            return url
        else:
            url = self.client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': blob_name},
                ExpiresIn=int(expiration.total_seconds())
            )
            return url

    def delete_file(self, blob_name: str):
        if self.use_gcs:
            blob = self.bucket.blob(blob_name)
            if blob.exists():
                blob.delete()
        else:
            self.client.delete_object(Bucket=self.bucket_name, Key=blob_name)
