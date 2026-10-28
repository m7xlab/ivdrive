"""Login must follow the 303 Skoda now returns after the email step."""

import httpx
import pytest

from app.services import skoda_bff_auth as auth

EMAIL_PAGE = '<form id="emailPasswordForm" action="/signin-service/v1/x/login/identifier"><input type="hidden" name="_csrf" value="c0"></form>'
PASSWORD_PAGE = "<script>csrf_token: 'tok1'; {\"hmac\":\"h1\",\"relayState\":\"r1\"}</script><form action=\"/signin-service/v1/x/login/authenticate\"></form>"


def _handler(redirect_after_identifier: bool, seen: dict):
    def handler(req: httpx.Request) -> httpx.Response:
        p = req.url.path
        if p.endswith("/oidc/v1/authorize"):
            return httpx.Response(302, headers={"location": "https://identity.example/signin"})
        if p == "/signin":
            return httpx.Response(200, text=EMAIL_PAGE)
        if p.endswith("/login/identifier"):
            if redirect_after_identifier:
                return httpx.Response(303, headers={"location": "/signin-service/v1/x/login/authenticate?relayState=r1"})
            return httpx.Response(200, text=PASSWORD_PAGE)
        if p.endswith("/login/authenticate") and req.method == "GET":
            return httpx.Response(200, text=PASSWORD_PAGE)
        if p.endswith("/login/authenticate") and req.method == "POST":
            seen["posted"] = req.content.decode()
            return httpx.Response(302, headers={"location": "myskoda://redirect/login?code=THECODE"})
        return httpx.Response(404)
    return handler


@pytest.mark.asyncio
@pytest.mark.parametrize("redirect", [True, False])
async def test_login_reaches_password_form_with_and_without_redirect(monkeypatch, redirect):
    seen: dict = {}
    real = httpx.AsyncClient
    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(_handler(redirect, seen)), **kw))
    monkeypatch.setattr(auth, "IDENTITY", "https://identity.example")

    async def fake_exchange(*, code, verifier):
        return {"access_token": f"tok-{code}"}

    monkeypatch.setattr(auth, "exchange_tokens", fake_exchange)
    tokens = await auth.login_with_password("a@b.c", "pw")
    assert tokens["access_token"] == "tok-THECODE"
    assert "_csrf=tok1" in seen["posted"] and "hmac=h1" in seen["posted"] and "password=pw" in seen["posted"]
