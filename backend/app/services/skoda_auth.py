from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from base64 import urlsafe_b64encode
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_IDENT_BASE = "https://identity.vwgroup.io"
_AUTHORIZE_URL = f"{_IDENT_BASE}/oidc/v1/authorize"

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Version/4.0 Chrome/74.0.3729.185 "
        "Mobile Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Upgrade-Insecure-Requests": "1",
    "X-Requested-With": "cz.skodaauto.connect",
}


def _generate_pkce() -> tuple[str, str]:
    verifier = urlsafe_b64encode(os.urandom(96)).decode("ascii")[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


class _EmailFormParser(HTMLParser):
    """Parse the emailPasswordForm to get action URL and hidden fields."""

    def __init__(self) -> None:
        super().__init__()
        self.action: str | None = None
        self.fields: dict[str, str] = {}
        self._in_form = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        d = dict(attrs)
        if tag == "form" and d.get("id") == "emailPasswordForm":
            self._in_form = True
            self.action = d.get("action")
        elif tag == "input" and self._in_form:
            name = d.get("name")
            if name:
                self.fields[name] = d.get("value", "") or ""


class _ScriptDataParser(HTMLParser):
    """Extract templateModel and csrf_token from <script> blocks."""

    def __init__(self) -> None:
        super().__init__()
        self._in_script = False
        self.csrf: str | None = None
        self.template_model: dict = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            self._in_script = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_script = False

    def handle_data(self, data: str) -> None:
        if not self._in_script:
            return

        tm_match = re.search(r"templateModel:\s*({.*?})\s*,?\s*\n", data, re.DOTALL)
        if tm_match:
            try:
                self.template_model = json.loads(tm_match.group(1))
            except json.JSONDecodeError:
                pass

        csrf_match = re.search(r"csrf_token:\s*'([^']+)'", data)
        if csrf_match:
            self.csrf = csrf_match.group(1)


class SkodaAuthClient:
    def __init__(self) -> None:
        self._session = httpx.AsyncClient(
            headers=_BROWSER_HEADERS,
            follow_redirects=True,
            timeout=30.0,
        )

    async def _reset_session(self) -> None:
        """Clear httpx connection pool before sensitive operations.

        Stale connections in the pool cause 'Remote end closed connection without
        response' errors when Skoda has already closed them server-side but
        httpx still thinks they're alive. Adopted from
        tillsteinbach/CarConnectivity-connector-skoda (my_skoda_session.py).
        """
        try:
            await self._session.aclose()
        except Exception:
            pass
        self._session = httpx.AsyncClient(
            headers=_BROWSER_HEADERS,
            follow_redirects=True,
            timeout=30.0,
        )

    async def login(self, username: str, password: str) -> dict:
        """Log in to MyŠkoda. All callers pass the shared guard (see login_guard): while Škoda is limiting
        logins nothing is sent, and a throttle or rejected password is recorded for everyone."""
        from app.services import login_guard as guard

        await guard.before_login()
        try:
            tokens = await self._login(username, password)
        except guard.LoginThrottledError as e:
            await guard.record_throttled()
            raise guard.LoginThrottledError(await guard.frozen_for() or guard.FIRST_FREEZE_S) from e
        except guard.LoginInvalidCredentialsError:
            await guard.record_invalid_credentials()
            raise
        await guard.record_success()
        return tokens

    async def _login(self, username: str, password: str) -> dict:
        from app.services import login_guard as guard

        verifier, challenge = _generate_pkce()
        client_id = settings.skoda_auth_client_id

        await self._reset_session()

        authorize_params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": settings.skoda_auth_redirect_uri,
            "scope": settings.skoda_auth_scope,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt": "login",
        }

        # Step 1: get the login page with email form
        resp = await self._session.get(_AUTHORIZE_URL, params=authorize_params)
        resp.raise_for_status()

        email_parser = _EmailFormParser()
        email_parser.feed(resp.text)

        if not email_parser.action:
            raise RuntimeError("Could not find emailPasswordForm on login page")

        email_url = urljoin(f"{_IDENT_BASE}/", email_parser.action)
        email_data = {**email_parser.fields, "email": username}
        logger.debug("Step 1: submitting email to %s", email_url)

        # Step 2: submit email, get password/credentials page
        resp = await self._session.post(email_url, data=email_data)
        resp.raise_for_status()

        script_parser = _ScriptDataParser()
        script_parser.feed(resp.text)

        tm = script_parser.template_model
        csrf = script_parser.csrf

        if not tm or not csrf:
            raise RuntimeError(
                "Could not extract templateModel/csrf from credentials page"
            )

        if tm.get("registerCredentialsPath") == "register":
            raise RuntimeError(
                f"Account {username} does not exist in Skoda Connect"
            )

        if tm.get("error"):
            raise RuntimeError(f"Login error from Skoda: {tm['error']}")

        post_action = tm.get("postAction")
        if not post_action:
            raise RuntimeError("No postAction found in templateModel")

        password_url = (
            f"{_IDENT_BASE}/signin-service/v1/{client_id}/{post_action}"
        )
        password_data = {
            "relayState": tm.get("relayState", ""),
            "hmac": tm.get("hmac", ""),
            "_csrf": csrf,
            "email": username,
            "password": password,
        }
        logger.debug("Step 2: submitting password to %s", password_url)

        # Step 3: submit password (no auto-follow -- we need to chase redirects for the code)
        pw_client = httpx.AsyncClient(
            headers=_BROWSER_HEADERS,
            follow_redirects=False,
            timeout=30.0,
            cookies=self._session.cookies,
        )

        try:
            resp = await pw_client.post(password_url, data=password_data)

            code: str | None = None
            max_redirects = 30
            for _ in range(max_redirects):
                if not resp.is_redirect:
                    break

                location = resp.headers.get("location", "")

                # Check for login errors in redirect params
                parsed = urlparse(location)
                qs = parse_qs(parsed.query)
                if "error" in qs:
                    error_code = qs["error"][0]
                    if error_code == "login.error.throttled":
                        raise guard.LoginThrottledError(guard.FIRST_FREEZE_S)
                    if error_code == "login.errors.password_invalid":
                        raise guard.LoginInvalidCredentialsError("Password is invalid")
                    raise guard.LoginError(f"Login error: {error_code}")

                if location.startswith(settings.skoda_auth_redirect_uri):
                    qs = parse_qs(parsed.query)
                    if "code" in qs:
                        code = qs["code"][0]
                    frag_qs = parse_qs(parsed.fragment)
                    if not code and "code" in frag_qs:
                        code = frag_qs["code"][0]
                    break

                if "terms-and-conditions" in location:
                    raise RuntimeError(
                        "Skoda requires accepting Terms & Conditions. "
                        "Please log in via the MySkoda app first."
                    )

                if "code" in qs:
                    code = qs["code"][0]
                    break

                if not location.startswith("http"):
                    location = urljoin(f"{_IDENT_BASE}/", location)

                resp = await pw_client.get(location)
        finally:
            await pw_client.aclose()

        if not code:
            raise RuntimeError(
                "Failed to obtain authorization code from redirect chain"
            )

        logger.info("Obtained authorization code, exchanging for tokens")

        # Step 4: exchange code for tokens
        exchange_url = (
            f"{settings.skoda_base_url}/api/v1/authentication/"
            "exchange-authorization-code?tokenType=CONNECT"
        )
        exchange_resp = await self._session.post(
            exchange_url,
            json={
                "code": code,
                "verifier": verifier,
                "redirectUri": settings.skoda_auth_redirect_uri,
            },
        )
        exchange_resp.raise_for_status()
        return exchange_resp.json()

    async def refresh(self, refresh_token: str) -> dict:
        refresh_url = (
            f"{settings.skoda_base_url}/api/v1/authentication/"
            "refresh-token?tokenType=CONNECT"
        )
        await self._reset_session()
        resp = await self._session.post(
            refresh_url, json={"token": refresh_token}
        )
        resp.raise_for_status()
        return resp.json()

    async def close(self) -> None:
        await self._session.aclose()
