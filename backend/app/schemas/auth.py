import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str | None = None
    invite_token: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginResponse(BaseModel):
    """Polymorphic login response: either tokens or a 2FA challenge."""

    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    requires_2fa: bool = False
    tfa_token: str | None = Field(None, alias="2fa_token")

    model_config = {"populate_by_name": True}


class RefreshRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str | None
    is_active: bool
    is_superuser: bool = False
    is_totp_enabled: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    display_name: str | None = None


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8)


# ── 2FA schemas ──────────────────────────────────────────────────────


class TwoFactorSetupResponse(BaseModel):
    """Returned by POST /2fa/setup.

    The ``secret`` and ``recovery_codes`` are shown to the user *once* and
    must be sent back in the subsequent POST /2fa/enable request so the
    backend never persists anything until the code is actually verified.
    """

    secret: str
    provisioning_uri: str
    qr_code_base64: str
    recovery_codes: list[str]


class TwoFactorEnableRequest(BaseModel):
    """Body for POST /2fa/enable.

    The frontend echoes back the ``secret`` and ``recovery_codes`` it received
    from /2fa/setup so the backend can verify the TOTP code and then atomically
    persist everything in one shot.
    """

    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    secret: str
    recovery_codes: list[str] = Field(min_length=10, max_length=10)


class TwoFactorVerifyRequest(BaseModel):
    """Legacy: kept for backwards compat; use TwoFactorEnableRequest for enable."""

    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class TwoFactorDisableRequest(BaseModel):
    password: str


class TwoFactorLoginRequest(BaseModel):
    tfa_token: str = Field(alias="2fa_token")
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")

    model_config = {"populate_by_name": True}


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class RecoveryCodeLoginRequest(BaseModel):
    """Body for POST /login/verify-recovery-code.

    Used when the user has lost access to their TOTP device and wants to
    authenticate with one of their pre-generated recovery codes instead.
    Each code is single-use and is permanently deleted after consumption.
    """

    tfa_token: str = Field(alias="2fa_token")
    recovery_code: str = Field(min_length=8, max_length=8)

    model_config = {"populate_by_name": True}
