import secrets
import uuid
from datetime import UTC, datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.announcement import Announcement
from app.models.invite import InviteRequest
from app.models.user import User
from app.api.v1.dependencies import get_current_superuser
from app.schemas.announcement import AnnouncementCreate, AnnouncementResponse
from app.schemas.invite import (
    InviteRequestResponse,
    InviteApprovalRequest,
    PromoteUserRequest
)
from app.config import settings
from app.services.email import send_invite_email

router = APIRouter()

@router.get("/invites", response_model=list[InviteRequestResponse])
async def list_invites(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser)
):
    result = await db.execute(select(InviteRequest).order_by(InviteRequest.created_at.desc()))
    return result.scalars().all()

@router.post("/invites/approve")
async def approve_invite(
    body: InviteApprovalRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser)
):
    result = await db.execute(select(InviteRequest).where(InviteRequest.email == body.email))
    invite = result.scalar_one_or_none()
    
    if not invite:
        raise HTTPException(status_code=404, detail="Invite request not found")
    
    if invite.status != "pending":
        raise HTTPException(status_code=400, detail=f"Invite is already {invite.status}")

    token = secrets.token_hex(32)
    invite.status = "approved"
    invite.token = token
    invite.approved_at = datetime.utcnow()
    
    await db.commit()
    
    invite_link = f"{settings.app_base_url}/register?token={token}"

    email_sent = send_invite_email(body.email, invite_link)

    return {
        "message": "Invite approved",
        "invite_link": invite_link,
        "email_sent": email_sent,
    }

@router.post("/invites/resend")
async def resend_invite(
    body: InviteApprovalRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
):
    result = await db.execute(select(InviteRequest).where(InviteRequest.email == body.email))
    invite = result.scalar_one_or_none()

    if not invite:
        raise HTTPException(status_code=404, detail="Invite request not found")

    if invite.status not in ("approved", "pending"):
        raise HTTPException(status_code=400, detail=f"Cannot resend invite with status '{invite.status}'")

    token = secrets.token_hex(32)
    invite.status = "approved"
    invite.token = token
    invite.approved_at = datetime.utcnow()

    await db.commit()

    invite_link = f"{settings.app_base_url}/register?token={token}"
    email_sent = send_invite_email(body.email, invite_link)

    return {
        "message": "Invite resent",
        "invite_link": invite_link,
        "email_sent": email_sent,
    }


@router.delete("/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_invite(
    invite_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
):
    result = await db.execute(select(InviteRequest).where(InviteRequest.id == invite_id))
    invite = result.scalar_one_or_none()

    if not invite:
        raise HTTPException(status_code=404, detail="Invite not found")

    await db.delete(invite)
    await db.commit()


@router.post("/invites/reject")
async def reject_invite(
    body: InviteApprovalRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
):
    result = await db.execute(select(InviteRequest).where(InviteRequest.email == body.email))
    invite = result.scalar_one_or_none()

    if not invite:
        raise HTTPException(status_code=404, detail="Invite request not found")

    if invite.status != "pending":
        raise HTTPException(status_code=400, detail=f"Invite is already {invite.status}")

    invite.status = "rejected"
    await db.commit()

    return {"message": f"Invite for {body.email} rejected"}


@router.get("/users")
async def list_users(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "display_name": u.display_name,
            "is_active": u.is_active,
            "is_superuser": u.is_superuser,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]


@router.post("/users/promote")
async def promote_user(
    body: PromoteUserRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser)
):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.is_superuser = True
    await db.commit()
    
    return {"message": f"User {body.email} promoted to superuser"}


@router.post("/users/demote")
async def demote_user(
    body: PromoteUserRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_superuser = False
    await db.commit()

    return {"message": f"User {body.email} demoted from superuser"}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await db.delete(user)
    await db.commit()


# ── Announcement endpoints ─────────────────────────────────────────────────────


@router.post("/announcements", response_model=AnnouncementResponse, status_code=status.HTTP_201_CREATED)
async def create_announcement(
    body: AnnouncementCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
):
    """Create a new system-wide announcement broadcast."""
    announcement = Announcement(
        title=body.title,
        message=body.message,
        type=body.type,
        expires_at=body.expires_at,
    )
    db.add(announcement)
    await db.commit()
    await db.refresh(announcement)
    return AnnouncementResponse(
        id=announcement.id,
        title=announcement.title,
        message=announcement.message,
        type=announcement.type,
        created_at=announcement.created_at,
        expires_at=announcement.expires_at,
        is_active=announcement.is_active,
    )


@router.get("/announcements", response_model=list[AnnouncementResponse])
async def list_announcements(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
):
    """List all announcements (including expired ones)."""
    result = await db.execute(select(Announcement).order_by(Announcement.created_at.desc()))
    announcements = result.scalars().all()
    return [
        AnnouncementResponse(
            id=a.id,
            title=a.title,
            message=a.message,
            type=a.type,
            created_at=a.created_at,
            expires_at=a.expires_at,
            is_active=a.is_active,
        )
        for a in announcements
    ]


@router.delete("/announcements/{announcement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_announcement(
    announcement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser),
):
    """Permanently remove an announcement."""
    result = await db.execute(select(Announcement).where(Announcement.id == announcement_id))
    announcement = result.scalar_one_or_none()
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    await db.delete(announcement)
    await db.commit()
