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
from app.database import async_session
import logging
from sqlalchemy import update, select

logger = logging.getLogger(__name__)

async def process_data_extraction(user_id: uuid.UUID, job_id: uuid.UUID, use_gcs: bool):
    try:
        async with async_session() as db:
            service = ExportService(db)
            await db.execute(update(ExtractionJob).where(ExtractionJob.id == job_id).values(status=ExtractionJobStatus.PROCESSING))
            await db.commit()

            zip_path = None
            enc_zip_path = None
            try:
                zip_path = await service.generate_user_export(user_id)
                if not zip_path:
                    raise Exception("No vehicle data found to export.")

                enc_zip_path = zip_path.replace(".zip", "_enc.zip")
                alphabet = string.ascii_letters + string.digits
                password = ''.join(secrets.choice(alphabet) for i in range(16))

                def encrypt_zip():
                    try:
                        with pyzipper.AESZipFile(enc_zip_path, 'w', compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as zf:
                            zf.setpassword(password.encode('utf-8'))
                            zf.setencryption(pyzipper.WZ_AES, nbits=256)
                            zf.write(zip_path, os.path.basename(zip_path))
                    finally:
                        password = None
                        if os.path.exists(zip_path):
                            os.remove(zip_path)
                    
                await asyncio.to_thread(encrypt_zip)

                storage = StorageProvider(use_gcs=use_gcs)
                blob_name = f"exports/{user_id}/{os.path.basename(enc_zip_path)}"
                await storage.upload_file(enc_zip_path, blob_name)

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
            finally:
                password = None
                if zip_path and os.path.exists(zip_path):
                    os.remove(zip_path)
                if enc_zip_path and os.path.exists(enc_zip_path):
                    os.remove(enc_zip_path)
            
    except Exception as e:
        async with async_session() as db:
            await db.execute(
                update(ExtractionJob).where(ExtractionJob.id == job_id)
                .values(status=ExtractionJobStatus.FAILED, error_message=str(e))
            )
            await db.commit()

async def cleanup_expired_extractions():
    use_gcs = os.getenv("USE_GCS_STORAGE", "false").lower() == "true"
    storage = StorageProvider(use_gcs=use_gcs)
    
    try:
        async with async_session() as db:
            query = select(ExtractionJob).where(ExtractionJob.expires_at < datetime.now(timezone.utc))
            result = await db.execute(query)
            expired_jobs = result.scalars().all()
            
            for job in expired_jobs:
                if job.file_url:
                    try:
                        await storage.delete_file(job.file_url)
                    except Exception as e:
                        logger.error(f"Failed to delete expired export {job.file_url}: {e}")
                
                await db.delete(job)
                
            if expired_jobs:
                await db.commit()
                logger.info(f"Cleaned up {len(expired_jobs)} expired extraction jobs.")
    except Exception as e:
        logger.error(f"Failed to run extraction job cleanup: {e}")
