import base64
import io
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
    password_fits,
    token_matches_user,
    verify_password,
)
from app.services import auth_guard
from app.services.email import send_password_reset_email
from app.services.fx import is_supported, rate_for
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


def _hash_recovery_code(code: str) -> str:
    """Keyed hash of a recovery code (v1.4.0). An unkeyed SHA-256 of an 8-character code is a
    minutes-long GPU job for anyone holding a database dump; the HMAC key is the server's
    encryption key, which a dump does not contain."""
    import hashlib
    import hmac
    key = settings.encryption_key.encode("utf-8")
    return "v2:" + hmac.new(key, code.strip().upper().encode("utf-8"), hashlib.sha256).hexdigest()


def _recovery_code_matches(candidate: str, stored: str) -> bool:
    """Codes issued before v1.4.0 are plain SHA-256 (no prefix) and stay valid until regenerated."""
    import hmac
    if stored.startswith("v2:"):
        return hmac.compare_digest(_hash_recovery_code(candidate), stored)
    return hmac.compare_digest(hash_field(candidate.strip().upper()), stored)


def _issue_tokens(response: Response, user: User) -> tuple[str, str]:
    """Mint the pair for this user's current token_version and set the cookies."""
    access_token = create_access_token(str(user.id), token_version=user.token_version)
    refresh_token = create_refresh_token(str(user.id), token_version=user.token_version)
    _set_session_cookies(response, access_token, refresh_token)
    return access_token, refresh_token


def _token_response(access_token: str, refresh_token: str) -> "TokenResponse":
    """Tokens travel in HttpOnly cookies; the JSON body repeats them only when a deployment
    switched AUTH_TOKENS_IN_BODY on for a non-browser client."""
    if settings.auth_tokens_in_body:
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)
    return TokenResponse(access_token="", refresh_token="")


def _password_or_422(password: str) -> None:
    if not password_fits(password):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="Password is too long (72 bytes maximum).")


def _set_session_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Set the session cookies for a freshly minted token pair.

    ``access_expires_at`` is deliberately readable by the browser client: it holds only a
    Unix timestamp, and the client uses it to refresh *before* the access token lapses so
    that no request is ever sent with a dead token. Without it the first request after the
    15-minute access lifetime (typically the announcements poll) was answered 401 and only
    then refreshed and retried, which left a "401" line in the browser console on every page
    left open for a while. The cookie outlives the access token so the client still knows the
    token is gone once it has expired.
    """
    access_max_age = settings.access_token_expire_minutes * 60
    refresh_max_age = settings.refresh_token_expire_days * 24 * 60 * 60
    expires_at = int(time.time()) + access_max_age
    csrf_token = str(uuid.uuid4())
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=access_max_age,
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=refresh_max_age,
    )
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        # Lives as long as the refresh token. As a session cookie it was gone after the browser
        # was closed while the persistent access token was still valid, so the first save after
        # reopening was refused "CSRF token missing" with nothing to trigger a refresh.
        max_age=refresh_max_age,
    )
    response.set_cookie(
        key="access_expires_at",
        value=str(expires_at),
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=refresh_max_age,
    )


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
            detail="This email address cannot be registered. If it is yours, use 'Forgot password'.",
        )

    _password_or_422(body.password)
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
        # Same answer as a new request: an invite form must not confirm which emails have accounts.
        return {"message": "Invite request received. We will notify you."}

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
async def login(request: Request, response: Response, body: LoginRequest, db: AsyncSession = Depends(get_db)):
    await auth_guard.check("login", body.email, request)
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or not password_fits(body.password) or not verify_password(body.password, user.password_hash):
        await auth_guard.failed("login", body.email, request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    await auth_guard.succeeded("login", body.email)

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

    access_token, refresh_token = _issue_tokens(response, user)
    if settings.auth_tokens_in_body:
        return LoginResponse(access_token=access_token, refresh_token=refresh_token)
    return LoginResponse(access_token="", refresh_token="")


@router.post("/login/verify-2fa", response_model=TokenResponse)
async def verify_2fa_login(request: Request, response: Response, body: TwoFactorLoginRequest, db: AsyncSession = Depends(get_db)):
    """Accept a temporary 2FA token + TOTP code and return full access tokens."""
    try:
        payload = decode_token(body.tfa_token)
    except JWTError:
        await auth_guard.failed("2fa", None, request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired 2FA token",
        )
    await auth_guard.check("2fa", payload.get("sub"), request)

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
        await auth_guard.failed("2fa", str(user.id), request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid 2FA code. Please try again.",
        )
    await auth_guard.succeeded("2fa", str(user.id))

    # Record the consumed window so the same code cannot be reused.
    user.last_totp_at = _totp_counter()
    await db.flush()

    access_token, refresh_token = _issue_tokens(response, user)
    return _token_response(access_token, refresh_token)


@router.post("/login/verify-recovery-code", response_model=TokenResponse)
async def verify_recovery_code_login(request: Request, response: Response, body: RecoveryCodeLoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticate using a one-time recovery code (for lost TOTP devices).

    The recovery code is permanently deleted after use.
    """
    try:
        payload = decode_token(body.tfa_token)
    except JWTError:
        await auth_guard.failed("2fa", None, request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired 2FA token",
        )
    await auth_guard.check("2fa", payload.get("sub"), request)

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

    matched = next((h for h in stored_codes if _recovery_code_matches(body.recovery_code, h)), None)
    if matched is None:
        await auth_guard.failed("2fa", str(user.id), request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid recovery code",
        )
    await auth_guard.succeeded("2fa", str(user.id))

    # Consume the code — it must never be usable again.
    updated_codes = [h for h in stored_codes if h != matched]
    user.recovery_codes = updated_codes if updated_codes else None
    await db.flush()

    access_token, refresh_token = _issue_tokens(response, user)
    return _token_response(access_token, refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response, body: RefreshRequest = None, db: AsyncSession = Depends(get_db)):
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

    # Re-validate the user against the DB before minting new tokens. A refresh
    # token alone must not keep a deactivated/deleted account alive for the
    # full 7-day refresh window.
    result = await db.execute(select(User).where(User.id == uuid.UUID(subject)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    if not token_matches_user(payload, user.token_version):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired, please log in again",
        )

    access_token, new_refresh = _issue_tokens(response, user)
    return _token_response(access_token, new_refresh)


@router.post("/logout", status_code=status.HTTP_200_OK)
async def logout(response: Response, request: Request, body: RefreshRequest = None):
    # In a stateless JWT system, true invalidation requires a blocklist, 
    # but deleting cookies prevents subsequent authenticated requests from the browser.
    response.delete_cookie(
        key="access_token", 
        httponly=True, 
        secure=settings.cookie_secure,
        samesite="lax"
    )
    response.delete_cookie(
        key="refresh_token", 
        httponly=True, 
        secure=settings.cookie_secure,
        samesite="lax"
    )
    response.delete_cookie(
        key="csrf_token", 
        httponly=False, 
        secure=settings.cookie_secure,
        samesite="lax"
    )
    response.delete_cookie(
        key="access_expires_at",
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return {"detail": "Successfully logged out"}


@router.post("/logout-all", status_code=status.HTTP_200_OK)
async def logout_everywhere(
    response: Response,
    request: Request,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Invalidate every session of this account (all devices), then clear this browser's cookies."""
    user.token_version = (user.token_version or 1) + 1
    await db.commit()
    return await logout(response, request)


# ── password reset (unauthenticated) ────────────────────────────────


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(request: Request, body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Initiate a password-reset flow.

    Always returns a generic message regardless of whether the email exists
    (prevents email enumeration attacks).
    """
    import logging
    logger = logging.getLogger(__name__)

    await auth_guard.check("forgot", body.email, request)
    await auth_guard.failed("forgot", body.email, request)  # every request counts: this is a mail sender
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is not None and user.is_active:
        token = create_password_reset_token(user.email)
        reset_link = f"{settings.app_base_url}/reset-password?token={token}"
        sent = send_password_reset_email(user.email, reset_link)
        if not sent:
            # Log but do not expose failure to caller
            logger.warning("Password reset email delivery failed for user %s", user.id)

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

    _password_or_422(body.new_password)
    user.password_hash = get_password_hash(body.new_password)
    user.token_version = (user.token_version or 1) + 1  # every existing session ends
    await db.commit()
    return {"detail": "Password has been reset successfully. You can now log in with your new password."}


# ── user profile ─────────────────────────────────────────────────────


async def _user_with_fx(user: User, db: AsyncSession) -> UserResponse:
    rate, as_of = await rate_for(db, user.default_currency)
    return UserResponse.model_validate(user).model_copy(
        update={"fx_rate": rate, "fx_as_of": as_of}
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await _user_with_fx(user, db)


@router.put("/me", response_model=UserResponse)
async def update_me(
    body: UserUpdateRequest,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if body.display_name is not None:
        user.display_name = body.display_name
    if body.default_currency is not None:
        code = body.default_currency.upper()
        if not await is_supported(db, code):
            raise HTTPException(status_code=400, detail=f"Unsupported currency: {code}")
        user.default_currency = code
    if body.unit_system is not None:
        user.unit_system = body.unit_system
    if body.show_commands is not None:
        user.show_commands = body.show_commands
    await db.flush()
    await db.refresh(user)
    return await _user_with_fx(user, db)



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
    response: Response,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password",
        )

    _password_or_422(body.new_password)
    user.password_hash = get_password_hash(body.new_password)
    # Other devices and any stolen refresh token stop working; this browser gets a fresh pair.
    user.token_version = (user.token_version or 1) + 1
    await db.flush()
    _issue_tokens(response, user)
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
    user.recovery_codes = [_hash_recovery_code(rc) for rc in body.recovery_codes]

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
