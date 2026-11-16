"""User-facing announcement / notification endpoints."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_active_user
from app.database import get_db
from app.models.announcement import Announcement, UserAnnouncement
from app.models.user import User
from app.schemas.announcement import UserAnnouncementResponse

router = APIRouter()


@router.get("/announcements/active", response_model=list[UserAnnouncementResponse])
async def get_active_announcements(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all active (non-expired, non-dismissed) announcements for the logged-in user."""
    now = datetime.now(UTC)

    # Fetch all non-expired announcements
    result = await db.execute(
        select(Announcement).where(
            (Announcement.expires_at.is_(None)) | (Announcement.expires_at > now)
        )
    )
    all_active = result.scalars().all()

    # Fetch dismissed announcement IDs for this user
    dismissed_result = await db.execute(
        select(UserAnnouncement).where(
            UserAnnouncement.user_id == user.id,
            UserAnnouncement.dismissed_at != None,  # noqa: E711
        )
    )
    dismissed_ids = {ua.announcement_id for ua in dismissed_result.scalars().all()}

    return [
        UserAnnouncementResponse(
            id=a.id,
            title=a.title,
            message=a.message,
            type=a.type,
            created_at=a.created_at,
            expires_at=a.expires_at,
            dismissed=a.id in dismissed_ids,
        )
        for a in all_active
    ]


@router.post("/announcements/{announcement_id}/dismiss", status_code=status.HTTP_200_OK)
async def dismiss_announcement(
    announcement_id: uuid.UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark an announcement as dismissed for the current user."""
    # Verify announcement exists
    result = await db.execute(select(Announcement).where(Announcement.id == announcement_id))
    announcement = result.scalar_one_or_none()
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")

    # Check if already dismissed
    ua_result = await db.execute(
        select(UserAnnouncement).where(
            UserAnnouncement.user_id == user.id,
            UserAnnouncement.announcement_id == announcement_id,
        )
    )
    user_announcement = ua_result.scalar_one_or_none()

    if user_announcement:
        if user_announcement.dismissed_at is not None:
            return {"detail": "Already dismissed"}
        user_announcement.dismissed_at = datetime.now(UTC)
    else:
        user_announcement = UserAnnouncement(
            user_id=user.id,
            announcement_id=announcement_id,
            dismissed_at=datetime.now(UTC),
        )
        db.add(user_announcement)

    await db.commit()
    return {"detail": "Dismissed"}
