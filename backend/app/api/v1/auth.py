import base64
import io
import json
import secrets
import string
import time
import uuid

import pyotp
import qrcode
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_active_user
from app.database import get_db
from app.models.user import User
from app.models.invite import InviteRequest
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    RecoveryCodeLoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
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
    create_password_reset_token,
    create_refresh_token,
    decode_password_reset_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.services.email import send_password_reset_email
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
    await db.commit()
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
async def login(response: Response, body: LoginRequest, db: AsyncSession = Depends(get_db)):
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

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))
    csrf_token = str(uuid.uuid4())
    
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=not settings.debug if hasattr(settings, "debug") else False,
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=not settings.debug if hasattr(settings, "debug") else False,
        samesite="lax",
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
    )
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=not settings.debug if hasattr(settings, "debug") else False,
        samesite="lax",
    )

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/login/verify-2fa", response_model=TokenResponse)
async def verify_2fa_login(response: Response, body: TwoFactorLoginRequest, db: AsyncSession = Depends(get_db)):
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

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))
    csrf_token = str(uuid.uuid4())
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=not settings.debug if hasattr(settings, "debug") else False, samesite="lax", max_age=settings.access_token_expire_minutes * 60)
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=not settings.debug if hasattr(settings, "debug") else False, samesite="lax", max_age=settings.refresh_token_expire_days * 24 * 60 * 60)
    response.set_cookie(key="csrf_token", value=csrf_token, httponly=False, secure=not settings.debug if hasattr(settings, "debug") else False, samesite="lax")
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/login/verify-recovery-code", response_model=TokenResponse)
async def verify_recovery_code_login(response: Response, body: RecoveryCodeLoginRequest, db: AsyncSession = Depends(get_db)):
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

    access_token = create_access_token(str(user.id))
    refresh_token = create_refresh_token(str(user.id))
    csrf_token = str(uuid.uuid4())
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=not settings.debug if hasattr(settings, "debug") else False, samesite="lax", max_age=settings.access_token_expire_minutes * 60)
    response.set_cookie(key="refresh_token", value=refresh_token, httponly=True, secure=not settings.debug if hasattr(settings, "debug") else False, samesite="lax", max_age=settings.refresh_token_expire_days * 24 * 60 * 60)
    response.set_cookie(key="csrf_token", value=csrf_token, httponly=False, secure=not settings.debug if hasattr(settings, "debug") else False, samesite="lax")
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response, body: RefreshRequest = None):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token and body and body.refresh_token:
        refresh_token = body.refresh_token
        
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token",
        )
    try:
        payload = decode_token(refresh_token)
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

    access_token = create_access_token(subject)
    new_refresh = create_refresh_token(subject)
    csrf_token = str(uuid.uuid4())
    response.set_cookie(key="access_token", value=access_token, httponly=True, secure=not settings.debug if hasattr(settings, "debug") else False, samesite="lax", max_age=settings.access_token_expire_minutes * 60)
    response.set_cookie(key="refresh_token", value=new_refresh, httponly=True, secure=not settings.debug if hasattr(settings, "debug") else False, samesite="lax", max_age=settings.refresh_token_expire_days * 24 * 60 * 60)
    response.set_cookie(key="csrf_token", value=csrf_token, httponly=False, secure=not settings.debug if hasattr(settings, "debug") else False, samesite="lax")
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
    )


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(response: Response, request: Request, body: RefreshRequest = None):
    # In a stateless JWT system, true invalidation requires a blocklist, 
    # but deleting cookies prevents subsequent authenticated requests from the browser.
    response.delete_cookie(
        key="access_token", 
        httponly=True, 
        secure=not settings.debug if hasattr(settings, "debug") else False,
        samesite="lax"
    )
    response.delete_cookie(
        key="refresh_token", 
        httponly=True, 
        secure=not settings.debug if hasattr(settings, "debug") else False,
        samesite="lax"
    )
    response.delete_cookie(
        key="csrf_token", 
        httponly=False, 
        secure=not settings.debug if hasattr(settings, "debug") else False,
        samesite="lax"
    )
    return {"detail": "Successfully logged out"}


# ── password reset (unauthenticated) ────────────────────────────────


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Initiate a password-reset flow.

    Always returns a generic message regardless of whether the email exists
    (prevents email enumeration attacks).
    """
    import logging
    logger = logging.getLogger(__name__)

    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is not None and user.is_active:
        token = create_password_reset_token(user.email)
        reset_link = f"{settings.app_base_url}/reset-password?token={token}"
        sent = send_password_reset_email(user.email, reset_link)
        if not sent:
            # Log but do not expose failure to caller
            logger.warning("Password reset email delivery failed for %s", user.email)

    return {"detail": "If an account with that email exists, a password reset link has been sent."}


@router.post("/reset-password", status_code=status.HTTP_200_OK)
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Complete the password-reset flow.

    Validates the JWT, hashes the new password, and updates the user record.
    The token is short-lived (30 min) and cannot be reused after expiry.
    """
    try:
        email, iat_dt = decode_password_reset_token(body.token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token.",
        )

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired password reset token.",
        )

    # Invalidate token if user's record was updated after the token was issued
    if iat_dt and user.updated_at and user.updated_at > iat_dt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token has been invalidated by a more recent account update.",
        )

    user.password_hash = get_password_hash(body.new_password)
    await db.commit()
    return {"detail": "Password has been reset successfully. You can now log in with your new password."}


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
    from fastapi import Response
    logger = logging.getLogger(__name__)
    logger.info(f"Account deletion executed for user_id={user.id}")
    await db.delete(user)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

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
