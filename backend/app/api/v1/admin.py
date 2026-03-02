import secrets
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.invite import InviteRequest
from app.models.user import User
from app.api.v1.dependencies import get_current_superuser
from app.schemas.invite import (
    InviteRequestResponse,
    InviteApprovalRequest,
    PromoteUserRequest
)
from app.config import settings

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

    token = secrets.token_urlsafe(32)
    invite.status = "approved"
    invite.token = token
    invite.approved_at = datetime.utcnow()
    
    await db.commit()
    
    invite_link = f"{settings.app_base_url}/register?token={token}"
    
    # TODO: Trigger SMTP email here
    
    return {"message": "Invite approved", "invite_link": invite_link}

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
