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
    secret: str
    provisioning_uri: str
    qr_code_base64: str


class TwoFactorVerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class TwoFactorDisableRequest(BaseModel):
    password: str


class TwoFactorLoginRequest(BaseModel):
    tfa_token: str = Field(alias="2fa_token")
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")

    model_config = {"populate_by_name": True}
