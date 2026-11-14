"""Admin AI: the environment carries endpoint + key only; provider/model choice lives in the admin."""
import pytest
from fastapi import HTTPException

from app.services import llm_providers as lp
from app.api.v1 import admin_ai

ENV_KEYS = ["OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL",
            "OLLAMA_BASE_URL", "GEMINI_API_KEY", "MINIMAX_API_KEY", "LLM_FALLBACK_PROVIDERS"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ENV_KEYS:
        monkeypatch.delenv(k, raising=False)


def test_catalog_lists_only_configured_providers_without_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://token-plan-ams.xiaomimimo.com/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-value")
    monkeypatch.setenv("OPENAI_MODEL", "mimo-v2.6-pro")
    cat = {c["name"]: c for c in lp.provider_catalog()}
    assert set(cat) == {"deterministic", "openai"}
    assert cat["openai"]["default_model"] == "mimo-v2.6-pro" and cat["openai"]["has_key"] is True
    assert "secret" not in str(cat)
    assert lp.known_provider_names() == {"deterministic", "openai"}


def test_a_tier_or_user_cannot_name_a_provider_the_server_has_not_got(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://x/v1")
    admin_ai._check_provider("openai")          # fine
    admin_ai._check_provider("deterministic")   # fine
    admin_ai._check_provider(None)              # not changing it: fine
    admin_ai._check_provider("")                # clearing: fine
    with pytest.raises(HTTPException) as e:
        admin_ai._check_provider("minimax")     # MINIMAX_API_KEY not set any more
    assert e.value.status_code == 422 and "openai" in e.value.detail


@pytest.mark.asyncio
async def test_usage_records_the_provider_that_answered_not_the_one_asked_for(monkeypatch):
    """Tier says 'minimax' (no key any more); openai answers via fallback. The log must say openai."""
    from app.api.v1 import chat as chat_mod
    monkeypatch.setenv("OPENAI_BASE_URL", "https://x/v1")
    monkeypatch.setenv("OPENAI_MODEL", "mimo-v2.6-pro")

    async def fake_complete(prov, model, system, user, **kw):
        return lp.LLMResult("4", 30, 5, 0)
    monkeypatch.setattr(chat_mod, "complete", fake_complete)
    stats: dict = {}
    out = await chat_mod.call_llm("2+2?", [], provider="minimax", model="MiniMax-M3", usage_stats=stats)
    assert out == "4"
    assert (stats["provider"], stats["model"]) == ("openai", "mimo-v2.6-pro")


@pytest.mark.asyncio
async def test_the_tiers_model_only_applies_to_the_tiers_own_provider(monkeypatch):
    from app.api.v1 import chat as chat_mod
    monkeypatch.setenv("OPENAI_BASE_URL", "https://x/v1")
    monkeypatch.setenv("OPENAI_MODEL", "mimo-v2.6-pro")
    seen = []

    async def fake_complete(prov, model, system, user, **kw):
        seen.append((prov.name, model))
        return lp.LLMResult("ok", 1, 1, 0)
    monkeypatch.setattr(chat_mod, "complete", fake_complete)
    stats: dict = {}
    await chat_mod.call_llm("hi", [], provider="openai", model="mimo-v2.6-flash", usage_stats=stats)
    assert seen == [("openai", "mimo-v2.6-flash")] and stats["model"] == "mimo-v2.6-flash"
