"""MyŠkoda BFF authentication (IdentityKit PKCE → mysmob CONNECT token).

Private API used only when the user connects MyŠkoda Login (optional advanced source).
"""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
import uuid
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

MYSMOB_BASE = "https://mysmob.api.connect.skoda-auto.cz"
IDENTITY = "https://identity.vwgroup.io"
TOKEN_TYPE = "CONNECT"
CLIENT_ID = "7f045eee-7003-4379-9968-9355ed2adb06@apps_vw-dilab_com"
X_CLIENT_ID = "afb0473b-6d82-42b8-bfea-cead338c46ef"
SCOPE = (
    "address badge birthdate cars driversLicense dealers email mileage mbb "
    "nationalIdentifier openid phone profession profile vin"
)
REDIRECT_URI = "myskoda://redirect/login/"
UA = "MySkoda/Android/8.17.0/260911002"


class BFFAuthError(Exception):
    """Base auth failure."""


class BFFAuthInvalidCredentials(BFFAuthError):
    """Wrong password / account rejected."""


class BFFAuthExpired(BFFAuthError):
    """Refresh token invalid or expired."""


def _pkce() -> tuple[str, str]:
    chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    verifier = "".join(secrets.choice(chars) for _ in range(64))
    raw = base64.b64encode(verifier.encode()).decode()
    verifier = raw.replace("+", "-").replace("/", "_").replace("=", "")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def _nonce() -> str:
    digest = hashlib.sha256(str(uuid.uuid4()).encode()).digest()
    return base64.b64encode(digest).decode().rstrip("=")


def _hidden(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in re.finditer(
        r"<input (?=[^>]* name=[\"']([^\"']*)|)(?=[^>]* value=[\"']([^\"']*)|)", html
    ):
        if m.group(1):
            out[m.group(1)] = m.group(2) or ""
    return out


def bearer_headers(access_token: str) -> dict[str, str]:
    return {
        "accept": "application/json",
        "user-agent": UA,
        "accept-language": "en",
        "authorization": f"Bearer {access_token}",
        "x-demo-mode": "false",
    }


async def exchange_tokens(*, code: str, verifier: str) -> dict:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{MYSMOB_BASE}/api/v1/authentication/exchange-authorization-code",
            params={"tokenType": TOKEN_TYPE},
            json={"code": code, "redirectUri": REDIRECT_URI, "verifier": verifier},
            headers={"accept": "*/*", "content-type": "application/json", "user-agent": UA},
        )
    if resp.status_code >= 400:
        raise BFFAuthError(f"token exchange failed: HTTP {resp.status_code}")
    data = resp.json()
    if not data.get("accessToken"):
        raise BFFAuthError("token exchange returned no accessToken")
    return data


async def refresh_tokens(refresh_token: str) -> dict:
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{MYSMOB_BASE}/api/v1/authentication/refresh-token",
            params={"tokenType": TOKEN_TYPE},
            json={"token": refresh_token},
            headers={"accept": "*/*", "content-type": "application/json", "user-agent": UA},
        )
    if resp.status_code >= 400:
        raise BFFAuthExpired(f"refresh failed: HTTP {resp.status_code}")
    data = resp.json()
    if not data.get("accessToken"):
        raise BFFAuthExpired("refresh returned no accessToken")
    return data


async def login_with_password(email: str, password: str) -> dict:
    """Full MyŠkoda login. Raises BFFAuthInvalidCredentials on bad password."""
    verifier, challenge = _pkce()
    params = {
        "client_id": CLIENT_ID,
        "scope": SCOPE,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "nonce": _nonce(),
        "state": str(uuid.uuid4()),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "x-requested-with": "cz.skodaauto.connect",
        "x-app-name": "cz.skodaauto.connect",
        "x-app-version": "8.0.0",
        "x-brand": "skoda",
        "x-client-id": X_CLIENT_ID,
    }
    async with httpx.AsyncClient(follow_redirects=False, timeout=60.0, headers=headers) as client:
        resp = await client.get(f"{IDENTITY}/oidc/v1/authorize", params=params)
        loc = resp.headers.get("location")
        if not loc:
            raise BFFAuthError("authorize did not redirect")
        cur = loc if loc.startswith("http") else urljoin(str(resp.url), loc)
        body = ""
        for _ in range(12):
            r = await client.get(cur)
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                nxt = r.headers["location"]
                cur = nxt if nxt.startswith("http") else urljoin(str(r.url), nxt)
                continue
            body = r.text
            break
        if "emailPasswordForm" not in body:
            raise BFFAuthError("login form not found")
        form = _hidden(body)
        form["email"] = email
        action_m = re.search(r'<form[^>]+action=["\']([^"\']+)', body)
        ident_url = (
            urljoin(cur, action_m.group(1))
            if action_m
            else f"{IDENTITY}/signin-service/v1/{CLIENT_ID}/login/identifier"
        )
        r = await client.post(
            ident_url,
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        body2 = r.text
        hidden = _hidden(body2)
        csrf = re.search(r"csrf_token: '([^']+)'", body2)
        hmac_m = re.search(r'"hmac":"([^"]+)"', body2)
        relay_m = re.search(r'"relayState":"([^"]+)"', body2)
        form2 = {
            "_csrf": (csrf.group(1) if csrf else hidden.get("_csrf", "")),
            "email": email,
            "password": password,
            "hmac": (hmac_m.group(1) if hmac_m else hidden.get("hmac", "")),
            "relayState": (relay_m.group(1) if relay_m else hidden.get("relayState", "")),
        }
        if not form2["_csrf"] and not form2["hmac"]:
            raise BFFAuthError("could not parse password form")
        action2 = re.search(r'<form[^>]+action=["\']([^"\']+)', body2)
        auth_url = (
            urljoin(cur, action2.group(1))
            if action2
            else f"{IDENTITY}/signin-service/v1/{CLIENT_ID}/login/authenticate"
        )
        r2 = await client.post(
            auth_url,
            data=form2,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        loc2 = r2.headers.get("location")
        if r2.status_code in (401, 403) or (
            loc2 and "error" in loc2.lower() and "code=" not in loc2
        ):
            raise BFFAuthInvalidCredentials("MyŠkoda rejected email or password")
        if not loc2:
            if r2.status_code >= 400:
                raise BFFAuthInvalidCredentials("MyŠkoda rejected email or password")
            raise BFFAuthError("authenticate did not redirect")
        next_url = loc2 if loc2.startswith("http") else urljoin(str(r2.url), loc2)
        code = None
        for _ in range(12):
            if "code=" in next_url or next_url.startswith("myskoda:"):
                code = (parse_qs(urlparse(next_url).query).get("code") or [None])[0]
                if code:
                    break
            rr = await client.get(next_url)
            if rr.status_code in (301, 302, 303, 307, 308) and rr.headers.get("location"):
                nxt = rr.headers["location"]
                next_url = nxt if nxt.startswith("http") else urljoin(str(rr.url), nxt)
                continue
            m = re.search(r"[?&#]code=([A-Za-z0-9._%-]+)", rr.text or "")
            code = m.group(1) if m else None
            break
        if not code:
            raise BFFAuthError("authorization code not captured")
    return await exchange_tokens(code=code, verifier=verifier)
