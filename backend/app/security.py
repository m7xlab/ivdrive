"""JWT token management and password hashing."""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from jwt import PyJWTError as JWTError

from app.config import settings


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")


def create_password_reset_token(subject: str) -> str:
    """Short-lived token (30 min) for password reset flows.

    ``subject`` is the user's email address (not user ID) so the token can be
    verified without a DB round-trip when decoding.
    """
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=30)
    to_encode = {"sub": subject, "iat": now, "exp": expire, "type": "password_reset"}
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_password_reset_token(token: str) -> tuple[str, datetime | None]:
    """Decode a password-reset JWT.

    Returns a tuple of (email, iat_datetime) on success.
    Raises ``JWTError`` on invalid/expired token or wrong token type.
    """
    payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    if payload.get("type") != "password_reset":
        raise JWTError("Invalid token type")
    sub = payload.get("sub")
    iat = payload.get("iat")
    if not sub:
        raise JWTError("Missing subject in token")
    
    iat_dt = datetime.fromtimestamp(iat, tz=UTC) if iat else None
    return sub, iat_dt


def create_2fa_token(subject: str) -> str:
    """Short-lived token (5 min) issued after password OK but before TOTP verification."""
    expire = datetime.now(UTC) + timedelta(minutes=5)
    to_encode = {"sub": subject, "exp": expire, "type": "2fa"}
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(subject: str, extra: dict | None = None, token_version: int = 1) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode = {"sub": subject, "exp": expire, "type": "access", "tv": int(token_version)}
    if extra:
        to_encode.update(extra)
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str, token_version: int = 1) -> str:
    expire = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)
    to_encode = {"sub": subject, "exp": expire, "type": "refresh", "tv": int(token_version)}
    return jwt.encode(to_encode, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def token_matches_user(payload: dict, user_token_version: int) -> bool:
    """A session token is only good while its ``tv`` claim equals the user's token_version.
    Tokens from before v1.4.0 carry no ``tv`` and are refused: the user logs in once."""
    return payload.get("tv") == int(user_token_version)


MAX_PASSWORD_BYTES = 72  # bcrypt's input limit; bcrypt 5 raises above it instead of truncating


def password_fits(password: str) -> bool:
    return len(password.encode("utf-8")) <= MAX_PASSWORD_BYTES


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token. Raises JWTError on failure."""
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


__all__ = [
    "JWTError",
    "verify_password",
    "get_password_hash",
    "create_password_reset_token",
    "decode_password_reset_token",
    "create_2fa_token",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
]
