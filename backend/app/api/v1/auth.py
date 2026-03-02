import base64
import io
import json
import secrets
import string
import time
import uuid

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_active_user
from app.database import get_db
from app.models.user import User
from app.models.invite import InviteRequest
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    RecoveryCodeLoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    TwoFactorDisableRequest,
    TwoFactorEnableRequest,
    TwoFactorLoginRequest,
    TwoFactorSetupResponse,
    TwoFactorVerifyRequest,
    UserResponse,
    UserUpdateRequest,
)
from app.schemas.invite import InviteRequestCreate
from app.config import settings
from app.security import (
    JWTError,
    create_2fa_token,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.services.crypto import decrypt_field, encrypt_field, hash_field

router = APIRouter()


# ── helpers ──────────────────────────────────────────────────────────


def _generate_qr_base64(provisioning_uri: str) -> str:
    """Return a base64-encoded PNG data URI of the provisioning URI QR code."""
    img = qrcode.make(provisioning_uri)
    with io.BytesIO() as buf:
        img.save(buf, format="PNG")
        b64_data = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64_data}"


def _generate_recovery_codes(n: int = 10) -> list[str]:
    """Generate ``n`` random 8-character alphanumeric (uppercase) recovery codes."""
    alphabet = string.ascii_uppercase + string.digits
    return ["".join(secrets.choice(alphabet) for _ in range(8)) for _ in range(n)]


def _totp_counter() -> int:
    """Return the current 30-second TOTP window counter (epoch // 30)."""
    return int(time.time() // 30)


def _check_totp_replay(user: User) -> None:
    """Raise 401 if the current TOTP window was already consumed by this user."""
    current = _totp_counter()
    if user.last_totp_at is not None and current <= user.last_totp_at:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="TOTP code already used — please wait for the next 30-second window.",
        )


# ── registration ─────────────────────────────────────────────────────


@router.get("/registration-mode")
async def registration_mode():
    """Public endpoint: returns current registration policy."""
    return {"mode": settings.service_registration}


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


# ── login / token ────────────────────────────────────────────────────


@router.post("/login", response_model=LoginResponse)
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

    # If 2FA is enabled, issue a short-lived challenge token instead of full tokens.
    if user.is_totp_enabled:
        return LoginResponse(
            requires_2fa=True,
            tfa_token=create_2fa_token(str(user.id)),
        )

    return LoginResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/login/verify-2fa", response_model=TokenResponse)
async def verify_2fa_login(body: TwoFactorLoginRequest, db: AsyncSession = Depends(get_db)):
    """Accept a temporary 2FA token + TOTP code and return full access tokens."""
    try:
        payload = decode_token(body.tfa_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired 2FA token",
        )

    if payload.get("type") != "2fa":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    if not user.is_totp_enabled or not user.totp_secret_enc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA is not enabled for this user")

    # Replay-attack prevention: reject codes from the same 30-s window.
    _check_totp_replay(user)

    secret = decrypt_field(user.totp_secret_enc)
    totp = pyotp.TOTP(secret)
    if not totp.verify(body.code, valid_window=1):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid 2FA code. Please try again.",
        )

    # Record the consumed window so the same code cannot be reused.
    user.last_totp_at = _totp_counter()
    await db.flush()

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/login/verify-recovery-code", response_model=TokenResponse)
async def verify_recovery_code_login(body: RecoveryCodeLoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate using a one-time recovery code (for lost TOTP devices).

    The recovery code is permanently deleted after use.
    """
    try:
        payload = decode_token(body.tfa_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired 2FA token",
        )

    if payload.get("type") != "2fa":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    if not user.is_totp_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA is not enabled for this user")

    stored_codes: list[str] = user.recovery_codes or []
    if not stored_codes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No recovery codes available for this account",
        )

    candidate_hash = hash_field(body.recovery_code.upper())
    if candidate_hash not in stored_codes:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid recovery code",
        )

    # Consume the code — it must never be usable again.
    updated_codes = [h for h in stored_codes if h != candidate_hash]
    user.recovery_codes = updated_codes if updated_codes else None
    await db.flush()

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


# ── user profile ─────────────────────────────────────────────────────


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



@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_me(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Account deletion executed for user_id={user.id}")
    await db.delete(user)
    await db.commit()
    return None

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


# ── 2FA management (authenticated) ──────────────────────────────────


@router.post("/2fa/setup", response_model=TwoFactorSetupResponse)
async def setup_2fa(
    user: User = Depends(get_current_active_user),
):
    """Generate a new TOTP secret + recovery codes and return them to the client.

    **Nothing is persisted at this stage.**  The frontend must store the
    ``secret`` and ``recovery_codes`` temporarily and echo them back in the
    subsequent ``POST /2fa/enable`` call together with a valid TOTP code.
    Only then will the backend save everything atomically.

    Can be called multiple times before enabling — each call regenerates both
    the secret and the recovery codes.
    """
    if user.is_totp_enabled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="2FA is already enabled. Disable it first to reconfigure.",
        )

    secret = pyotp.random_base32()
    provisioning_uri = pyotp.TOTP(secret).provisioning_uri(
        name=user.email,
        issuer_name="iVDrive",
    )
    recovery_codes = _generate_recovery_codes(10)

    # Do NOT persist anything — the client sends it all back in /2fa/enable.
    return TwoFactorSetupResponse(
        secret=secret,
        provisioning_uri=provisioning_uri,
        qr_code_base64=_generate_qr_base64(provisioning_uri),
        recovery_codes=recovery_codes,
    )


@router.post("/2fa/enable", status_code=status.HTTP_200_OK)
async def enable_2fa(
    body: TwoFactorEnableRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Verify the initial TOTP code and atomically enable 2FA.

    The client must supply the ``secret`` and ``recovery_codes`` that were
    returned by ``POST /2fa/setup``.  The TOTP code is verified against the
    provided secret *before* anything is written to the database, ensuring the
    setup is fully atomic.
    """
    if user.is_totp_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA is already enabled")

    # Verify the TOTP code against the supplied secret (not yet in DB).
    totp = pyotp.TOTP(body.secret)
    if not totp.verify(body.code, valid_window=1):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid 2FA code. Please try again.",
        )

    # Replay-attack prevention for the enabling step.
    _check_totp_replay(user)

    # All good — atomically persist everything.
    user.totp_secret_enc = encrypt_field(body.secret)
    user.is_totp_enabled = True
    user.last_totp_at = _totp_counter()

    # Hash the recovery codes before storing them.
    user.recovery_codes = [hash_field(rc.upper()) for rc in body.recovery_codes]

    await db.flush()
    return {"detail": "2FA has been enabled successfully"}


@router.post("/2fa/disable", status_code=status.HTTP_200_OK)
async def disable_2fa(
    body: TwoFactorDisableRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Disable 2FA. Requires current password for confirmation."""
    if not user.is_totp_enabled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA is not enabled")

    if not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect password",
        )

    user.is_totp_enabled = False
    user.totp_secret_enc = None
    user.last_totp_at = None
    user.recovery_codes = None
    await db.flush()
    return {"detail": "2FA has been disabled"}
