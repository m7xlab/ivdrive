from datetime import datetime, timedelta, UTC
from uuid import UUID
import logging
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vehicle import ConnectorSession, ConnectorAuthEvent
from app.services.skoda_auth import SkodaAuthClient
from app.services.crypto import encrypt_field, decrypt_field

logger = logging.getLogger(__name__)

class AuthRequiredError(Exception):
    pass

class SkodaTokenLifecycle:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def _record_event(self, cs: ConnectorSession, event_type: str, reason: str | None = None, details: dict | None = None) -> None:
        event = ConnectorAuthEvent(
            session_id=cs.id,
            event_type=event_type,
            reason=reason,
            details=details or {}
        )
        self.session.add(event)

    def _update_tokens(self, cs: ConnectorSession, tokens: dict, method: str) -> None:
        access_token = tokens.get("accessToken") or tokens.get("access_token")
        refresh_token = tokens.get("refreshToken") or tokens.get("refresh_token")
        
        if not access_token or not refresh_token:
            raise AuthRequiredError("Auth response missing required tokens")
            
        cs.access_token_encrypted = encrypt_field(access_token)
        cs.refresh_token_encrypted = encrypt_field(refresh_token)
        expires_in = tokens.get("expiresIn") or tokens.get("expires_in", 3600)
        now = datetime.now(UTC)
        cs.token_expires_at = now + timedelta(seconds=expires_in)
        cs.last_auth_at = now
        cs.last_auth_method = method

    async def ensure_valid_token(self, cs: ConnectorSession, username: str, password: str | None = None, force_refresh: bool = False, force_login: bool = False) -> str:
        """
        Ensures the token is valid. Returns access_token.
        If force_refresh is True, or if the access token is near expiry, tries to refresh.
        If force_login is True, immediately attempts a silent login.
        If refresh fails with 401/403/400, and secure_mode is ON (password provided), falls back to silent relogin.
        Raises AuthRequiredError if completely failed.
        """
        now = datetime.now(UTC)

        if cs.backoff_until and cs.backoff_until > now:
            raise AuthRequiredError(f"Backing off until {cs.backoff_until}")

        if force_login:
            if cs.secure_mode and password:
                logger.info(f"Force login requested, attempting silent login for {cs.id}")
                return await self._silent_login(cs, username, password)
            else:
                cs.status = "auth_failed"
                cs.needs_user_reauth_reason = "Force login requested but secure mode is OFF."
                await self._record_event(cs, "auth_required", "secure_mode off")
                raise AuthRequiredError("Force login requested but secure mode is OFF")

        if not cs.access_token_encrypted or not cs.refresh_token_encrypted:
            raise AuthRequiredError("Missing tokens")

        access_token = decrypt_field(cs.access_token_encrypted)
        
        if not force_refresh and cs.token_expires_at and cs.token_expires_at > now + timedelta(minutes=2):
            return access_token

        refresh_token = decrypt_field(cs.refresh_token_encrypted)
        logger.info(f"Token expired/refresh requested for session {cs.id}, attempting refresh...")
        
        try:
            auth_client = SkodaAuthClient()
            try:
                tokens = await auth_client.refresh(refresh_token)
                self._update_tokens(cs, tokens, method="refresh")
                await self._record_event(cs, "refresh_success")
                cs.status = "pending"
                cs.consecutive_auth_failures = 0
                cs.backoff_until = None
                cs.last_auth_error = None
                cs.needs_user_reauth_reason = None
                return decrypt_field(cs.access_token_encrypted)
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403, 400):
                    await self._record_event(cs, "refresh_failed", str(e), {"status_code": e.response.status_code})
                    logger.warning(f"Refresh failed for {cs.id} with {e.response.status_code}")
                    if cs.secure_mode and password:
                        logger.info(f"Secure mode ON, attempting silent login for {cs.id}")
                        return await self._silent_login(cs, username, password)
                    else:
                        cs.status = "auth_failed"
                        cs.needs_user_reauth_reason = (
                            "Session expired and MyŠkoda login is not saved. "
                            "Update your login in Settings → Vehicles → Login."
                        )
                        cs.last_auth_error = str(e)
                        await self._record_event(cs, "auth_required", "secure_mode off")
                        raise AuthRequiredError("MyŠkoda session expired — update login in Settings.")
                elif e.response.status_code >= 500:
                    await self._record_event(cs, "refresh_transient_error", str(e))
                    raise
                else:
                    raise
            except httpx.TimeoutException as e:
                await self._record_event(cs, "refresh_timeout")
                raise
            finally:
                await auth_client.close()
        except Exception:
            raise

    async def _silent_login(self, cs: ConnectorSession, username: str, password: str) -> str:
        auth_client = SkodaAuthClient()
        try:
            tokens = await auth_client.login(username, password)
            self._update_tokens(cs, tokens, method="silent_login")
            await self._record_event(cs, "silent_login_success")
            cs.status = "pending"
            cs.consecutive_auth_failures = 0
            cs.backoff_until = None
            cs.last_auth_error = None
            cs.needs_user_reauth_reason = None
            return decrypt_field(cs.access_token_encrypted)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                cs.consecutive_auth_failures += 1
                backoff_minutes = min(15 * (2 ** (cs.consecutive_auth_failures - 1)), 6 * 60)
                cs.backoff_until = datetime.now(UTC) + timedelta(minutes=backoff_minutes)
                await self._record_event(cs, "silent_login_throttled", str(e), {"backoff": backoff_minutes})
                cs.last_auth_error = "Throttled by Skoda"
                raise AuthRequiredError("Throttled during silent login")
            elif e.response.status_code in (401, 403, 400):
                cs.status = "auth_failed"
                cs.needs_user_reauth_reason = (
                    "Could not log in to MyŠkoda with the saved email and password. "
                    "Update your login in Settings → Vehicles → Login."
                )
                cs.last_auth_error = str(e)
                await self._record_event(cs, "silent_login_failed", str(e))
                raise AuthRequiredError(
                    "MyŠkoda email or password is incorrect — update login in Settings."
                )
            raise
        finally:
            await auth_client.close()
