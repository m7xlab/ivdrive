from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_active_user
from app.database import get_db
from app.models.user import User
from app.models.invite import InviteRequest
from app.schemas.auth import (
    LoginRequest,
    PasswordChangeRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
    UserUpdateRequest,
)
from app.schemas.invite import InviteRequestCreate
from app.config import settings
from app.security import (
    JWTError,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # 1. Check if invite-only registration is enabled
    if settings.service_registration == "invite_only":
        if not body.invite_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invite token required for registration",
            )
        
        # Validate token
        res = await db.execute(
            select(InviteRequest)
            .where(InviteRequest.token == body.invite_token)
            .where(InviteRequest.status == "approved")
        )
        invite = res.scalar_one_or_none()
        if not invite:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired invite token",
            )
        
        # Verify email matches (optional security layer)
        if invite.email != body.email:
             raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Registration email must match the invitation email",
            )

        # Mark invite as used
        invite.status = "used"

    # 2. Proceed with user creation
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=body.email,
        password_hash=get_password_hash(body.password),
        display_name=body.display_name,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


@router.post("/invite-request", status_code=status.HTTP_202_ACCEPTED)
async def request_invite(body: InviteRequestCreate, db: AsyncSession = Depends(get_db)):
    # Check if user already exists
    res_u = await db.execute(select(User).where(User.email == body.email))
    if res_u.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User already registered")

    # Check if request already exists
    res_i = await db.execute(select(InviteRequest).where(InviteRequest.email == body.email))
    if res_i.scalar_one_or_none():
        return {"message": "Invite request already received. We will notify you."}

    # Add new request
    invite = InviteRequest(email=body.email)
    db.add(invite)
    await db.commit()
    return {"message": "Invite request submitted successfully"}


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest):
    try:
        payload = decode_token(body.refresh_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    subject = payload.get("sub")
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    return TokenResponse(
        access_token=create_access_token(subject),
        refresh_token=create_refresh_token(subject),
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(body: RefreshRequest):
    return {"detail": "Successfully logged out"}


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_active_user)):
    return user


@router.put("/me", response_model=UserResponse)
async def update_me(
    body: UserUpdateRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if body.display_name is not None:
        user.display_name = body.display_name
    await db.flush()
    await db.refresh(user)
    return user


@router.put("/me/password", status_code=status.HTTP_200_OK)
async def change_password(
    body: PasswordChangeRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password",
        )

    user.password_hash = get_password_hash(body.new_password)
    await db.flush()
    return {"detail": "Password updated successfully"}
