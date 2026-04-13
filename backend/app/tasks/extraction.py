import asyncio
import os
import secrets
import string
import uuid
import pyzipper
from datetime import datetime, timezone, timedelta
from app.services.export import ExportService
from app.models.extraction_job import ExtractionJob, ExtractionJobStatus
from app.services.storage import StorageProvider
from app.database import async_sessionmaker
from sqlalchemy import update

async def process_data_extraction(user_id: uuid.UUID, job_id: uuid.UUID, use_gcs: bool):
    try:
        async with async_sessionmaker() as db:
            service = ExportService(db)
            await db.execute(update(ExtractionJob).where(ExtractionJob.id == job_id).values(status=ExtractionJobStatus.PROCESSING))
            await db.commit()

            zip_path = await service.generate_user_export(user_id)
            if not zip_path:
                raise Exception("No vehicle data found to export.")

            alphabet = string.ascii_letters + string.digits
            password = ''.join(secrets.choice(alphabet) for i in range(16))
            enc_zip_path = zip_path.replace(".zip", "_enc.zip")

            def encrypt_zip():
                with pyzipper.AESZipFile(enc_zip_path, 'w', compression=pyzipper.ZIP_LZMA, encryption=pyzipper.WZ_AES) as zf:
                    zf.setpassword(password.encode('utf-8'))
                    zf.write(zip_path, os.path.basename(zip_path))
                
            await asyncio.to_thread(encrypt_zip)
            os.remove(zip_path)

            storage = StorageProvider(use_gcs=use_gcs)
            blob_name = f"exports/{user_id}/{os.path.basename(enc_zip_path)}"
            await storage.upload_file(enc_zip_path, blob_name)
            
            os.remove(enc_zip_path)

            expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
            await db.execute(
                update(ExtractionJob).where(ExtractionJob.id == job_id)
                .values(
                    status=ExtractionJobStatus.COMPLETED, 
                    file_url=blob_name,
                    password=password,
                    expires_at=expires_at
                )
            )
            await db.commit()
            
    except Exception as e:
        async with async_sessionmaker() as db:
            await db.execute(
                update(ExtractionJob).where(ExtractionJob.id == job_id)
                .values(status=ExtractionJobStatus.FAILED, error_message=str(e))
            )
            await db.commit()
