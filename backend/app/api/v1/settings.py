import uuid
import os
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_active_user
from app.database import get_db
from app.models.geofence import Geofence
from app.models.user import User
from app.models.extraction_job import ExtractionJob, ExtractionJobStatus
from app.schemas.geofence import GeofenceCreate, GeofenceResponse, GeofenceUpdate
from app.services.export import ExportService
from app.tasks.extraction import process_data_extraction
from app.services.storage import StorageProvider

router = APIRouter()

# ── Data Export ─────────────────────────────────────────────────────────────

@router.get("/export/config", status_code=status.HTTP_200_OK)
async def get_export_config(
    user: User = Depends(get_current_active_user),
):
    use_gcs = os.getenv("USE_GCS_STORAGE", "false").lower() == "true"
    use_s3 = os.getenv("USE_S3_STORAGE", "false").lower() == "true"
    
    export_enabled = use_gcs or use_s3
    return {"export_enabled": export_enabled}

@router.post("/export", status_code=status.HTTP_202_ACCEPTED)
async def request_data_export(
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Triggers a 1-year data export for the user asynchronously.
    """
    job = ExtractionJob(user_id=user.id, status=ExtractionJobStatus.PENDING)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    
    use_gcs = os.getenv("USE_GCS_STORAGE", "false").lower() == "true"
    
    background_tasks.add_task(process_data_extraction, user.id, job.id, use_gcs)
    
    return {"message": "Export initiated", "job_id": job.id}

@router.get("/export/status", status_code=status.HTTP_200_OK)
async def get_data_export_status(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ExtractionJob).where(ExtractionJob.user_id == user.id).order_by(ExtractionJob.created_at.desc())
    )
    jobs = result.scalars().all()
    return [{"job_id": j.id, "status": j.status, "created_at": j.created_at} for j in jobs]

@router.get("/export/{job_id}/download", status_code=status.HTTP_200_OK)
async def get_download_link(
    job_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ExtractionJob).where(ExtractionJob.id == job_id, ExtractionJob.user_id == user.id))
    job = result.scalar_one_or_none()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != ExtractionJobStatus.COMPLETED or not job.file_url:
        raise HTTPException(status_code=400, detail="Export not completed yet")
        
    use_gcs = os.getenv("USE_GCS_STORAGE", "false").lower() == "true"
    try:
        storage = StorageProvider(use_gcs=use_gcs)
        download_url = storage.generate_download_url(job.file_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    return {
        "url": download_url,
        "password": job.password,
        "expires_at": job.expires_at
    }

# ── Geofences ───────────────────────────────────────────────────────────────

@router.get("/geofences", response_model=list[GeofenceResponse])
async def list_geofences(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Geofence).where(Geofence.user_id == user.id)
    )
    return result.scalars().all()


@router.post(
    "/geofences",
    response_model=GeofenceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_geofence(
    body: GeofenceCreate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    geofence = Geofence(
        user_id=user.id,
        name=body.name,
        latitude=body.latitude,
        longitude=body.longitude,
        radius_meters=body.radius_meters,
        address=body.address,
    )
    db.add(geofence)
    await db.flush()
    return geofence


@router.put("/geofences/{geofence_id}", response_model=GeofenceResponse)
async def update_geofence(
    geofence_id: uuid.UUID,
    body: GeofenceUpdate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Geofence).where(
            Geofence.id == geofence_id, Geofence.user_id == user.id
        )
    )
    geofence = result.scalar_one_or_none()
    if not geofence:
        raise HTTPException(status_code=404, detail="Geofence not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(geofence, field, value)
    await db.flush()
    return geofence


@router.delete(
    "/geofences/{geofence_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_geofence(
    geofence_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Geofence).where(
            Geofence.id == geofence_id, Geofence.user_id == user.id
        )
    )
    geofence = result.scalar_one_or_none()
    if not geofence:
        raise HTTPException(status_code=404, detail="Geofence not found")
    await db.delete(geofence)
    await db.flush()
