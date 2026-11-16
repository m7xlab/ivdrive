"""PyJWT replaced python-jose in v1.4.0. Tokens issued by the old library before the
deploy must still decode, and the failure modes callers catch must stay the same."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app import security
from app.config import settings

# Minted once with python-jose 3.5.0: HS256, sub=user-123, type=access, exp=2099-01-01.
_SECRET = "unit-test-secret-not-used-anywhere-else-0123456789"
_JOSE_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJ1c2VyLTEyMyIsImlhdCI6MTc5NDcwMDgwMCwiZXhwIjo0MDcwOTA4ODAwLCJ0eXBlIjoiYWNjZXNzIn0."
    "2xTjAgqJ5Z3paKKeWGbh7lAekF0qaGyUIF45gefvhOY"
)


@pytest.fixture
def test_secret(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret_key", _SECRET)
    monkeypatch.setattr(settings, "jwt_algorithm", "HS256")


def test_token_minted_by_python_jose_still_decodes(test_secret):
    payload = security.decode_token(_JOSE_TOKEN)
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"


def test_round_trip_and_type_claims(test_secret):
    access = security.decode_token(security.create_access_token("u1", {"role": "x"}))
    refresh = security.decode_token(security.create_refresh_token("u1"))
    assert (access["sub"], access["type"], access["role"]) == ("u1", "access", "x")
    assert refresh["type"] == "refresh"
    email, iat = security.decode_password_reset_token(security.create_password_reset_token("a@b.c"))
    assert email == "a@b.c" and iat is not None and iat.tzinfo is not None


def test_failures_raise_the_jwterror_callers_catch(test_secret):
    with pytest.raises(security.JWTError):
        security.decode_token(_JOSE_TOKEN[:-3] + "AAA")  # bad signature
    expired = jwt.encode(
        {"sub": "u", "exp": datetime.now(UTC) - timedelta(seconds=5), "type": "access"},
        _SECRET, algorithm="HS256",
    )
    with pytest.raises(security.JWTError):
        security.decode_token(expired)
    # Algorithm pinning: a token signed with another algorithm is rejected even with the right key.
    other = jwt.encode({"sub": "u", "type": "access"}, _SECRET, algorithm="HS512")
    with pytest.raises(security.JWTError):
        security.decode_token(other)
    wrong_type = security.create_access_token("a@b.c")
    with pytest.raises(security.JWTError):
        security.decode_password_reset_token(wrong_type)
