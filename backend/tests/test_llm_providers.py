"""Provider registry + wire formats. No network: httpx.MockTransport."""

import json

import httpx
import pytest

from app.services import llm_providers as lp

ENV_KEYS = [
    "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL", "ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL",
    "ANTHROPIC_MODEL", "OLLAMA_BASE_URL", "OLLAMA_MODEL", "OLLAMA_API_KEY", "GEMINI_API_KEY",
    "GEMINI_BASE_URL", "GEMINI_MODEL", "MINIMAX_API_KEY", "MINIMAX_BASE_URL", "MINIMAX_MODEL",
    "LLM_FALLBACK_PROVIDERS", "LLM_TIMEOUT_SECONDS",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ENV_KEYS:
        monkeypatch.delenv(k, raising=False)


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_nothing_configured_means_no_providers_and_gemini_is_optional():
    assert lp.configured_providers() == {}
    assert lp.provider_order("gemini") == []


def test_placeholder_keys_do_not_enable_a_provider(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "CHANGE_ME")
    monkeypatch.setenv("MINIMAX_API_KEY", "")
    assert lp.configured_providers() == {}


def test_gemini_only_when_key_set(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert list(lp.configured_providers()) == ["gemini"]


def test_ollama_base_url_gets_v1_and_needs_no_key(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://nas:11434/")
    p = lp.configured_providers()["ollama"]
    assert (p.base_url, p.api_key, p.kind) == ("http://nas:11434/v1", "", "openai")


def test_fallback_order_and_none(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "a")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "b")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://x")
    assert [p.name for p in lp.provider_order("ollama")] == ["ollama", "openai", "anthropic"]
    assert [p.name for p in lp.provider_order("missing")] == ["openai", "anthropic", "ollama"]
    monkeypatch.setenv("LLM_FALLBACK_PROVIDERS", "none")
    assert [p.name for p in lp.provider_order("anthropic")] == ["anthropic"]
    monkeypatch.setenv("LLM_FALLBACK_PROVIDERS", "openai")
    assert [p.name for p in lp.provider_order("anthropic")] == ["anthropic", "openai"]


@pytest.mark.asyncio
async def test_openai_compatible_custom_host_without_key(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://lmstudio:1234/v1")
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers.get("authorization"), json.loads(req.content)
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "hi"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3, "prompt_tokens_details": {"cached_tokens": 2}},
        })

    p = lp.configured_providers()["openai"]
    res = await lp.complete(p, "qwen2.5", "sys", "q", client=_client(handler))
    assert seen["url"] == "http://lmstudio:1234/v1/chat/completions" and seen["auth"] is None
    assert seen["body"]["model"] == "qwen2.5" and seen["body"]["messages"][0] == {"role": "system", "content": "sys"}
    assert (res.text, res.prompt_tokens, res.completion_tokens, res.cached_tokens) == ("hi", 7, 3, 2)


@pytest.mark.asyncio
async def test_anthropic_wire_format_and_custom_host(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://proxy.local/")
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["h"], seen["body"] = str(req.url), req.headers, json.loads(req.content)
        return httpx.Response(200, json={
            "content": [{"type": "text", "text": "Hel"}, {"type": "text", "text": "lo"}],
            "usage": {"input_tokens": 11, "output_tokens": 5, "cache_read_input_tokens": 4},
        })

    p = lp.configured_providers()["anthropic"]
    res = await lp.complete(p, "claude-x", "sys", "q", client=_client(handler))
    assert seen["url"] == "https://proxy.local/v1/messages"
    assert seen["h"]["x-api-key"] == "sk-ant" and seen["h"]["anthropic-version"] == "2023-06-01"
    assert seen["body"]["system"] == "sys" and seen["body"]["messages"] == [{"role": "user", "content": "q"}]
    assert (res.text, res.prompt_tokens, res.completion_tokens, res.cached_tokens) == ("Hello", 11, 5, 4)


@pytest.mark.asyncio
async def test_gemini_uses_header_key_and_requested_model(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gk")
    seen = {}

    def handler(req: httpx.Request):
        seen["url"], seen["key"] = str(req.url), req.headers.get("x-goog-api-key")
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
            "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 2},
        })

    p = lp.configured_providers()["gemini"]
    res = await lp.complete(p, "gemini-3.1-pro-preview", "s", "q", client=_client(handler))
    assert "gemini-3.1-pro-preview:generateContent" in seen["url"] and "gk" not in seen["url"]
    assert seen["key"] == "gk" and res.text == "ok"


@pytest.mark.asyncio
async def test_http_error_becomes_llmerror_without_leaking_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret")
    p = lp.configured_providers()["openai"]
    with pytest.raises(lp.LLMError) as e:
        await lp.complete(p, "m", "s", "q", client=_client(lambda r: httpx.Response(401, text="bad key")))
    assert "401" in str(e.value) and "sk-secret" not in str(e.value)


@pytest.mark.asyncio
async def test_call_llm_uses_tier_model_then_fallback_default(monkeypatch):
    from app.api.v1 import chat

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://x")
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    calls = []

    async def fake_complete(prov, model, system, user, **kw):
        calls.append((prov.name, model))
        if prov.name == "ollama":
            raise lp.LLMError("ollama down")
        return lp.LLMResult("answer", 1, 2, 0)

    monkeypatch.setattr(chat, "complete", fake_complete)
    usage: dict = {}
    out = await chat.call_llm("hello", [], provider="ollama", model="llama3.2", usage_stats=usage)
    assert out == "answer"
    assert calls == [("ollama", "llama3.2"), ("openai", "gpt-4o-mini")]
    assert usage == {"prompt_tokens": 1, "completion_tokens": 2, "cached_tokens": 0}


@pytest.mark.asyncio
async def test_call_llm_explains_when_nothing_is_configured():
    from app.api.v1 import chat
    out = await chat.call_llm("hello", [], provider="gemini", model=None)
    assert "No AI provider is configured" in out


def test_unknown_model_cost_is_zero_known_is_priced():
    from app.services.ai_gate import estimate_cost_usd
    assert estimate_cost_usd("llama3.2:3b", 10_000, 5_000) == 0.0
    assert estimate_cost_usd("MiniMax-M3", 1_000_000, 0) == 0.6


@pytest.mark.asyncio
async def test_compat_embeddings_enforce_768_dims(monkeypatch):
    from app.services import ai_embeddings as ae
    monkeypatch.setenv("EMBEDDING_BASE_URL", "http://ollama:11434")
    monkeypatch.setenv("EMBEDDING_MODEL", "nomic-embed-text")
    real = httpx.AsyncClient

    def handler(req: httpx.Request):
        n = len(json.loads(req.content)["input"])
        return httpx.Response(200, json={"data": [{"index": i, "embedding": [0.1] * (768 if i == 0 else 384)} for i in range(n)]})

    monkeypatch.setattr(ae.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler)))
    good, bad = await ae.batch_openai_compat_embeddings(["a", "b"], "ollama", 768)
    assert len(good) == 768 and bad is None
    vec, model = await ae.generate_embedding("a", provider="ollama")
    assert model == "nomic-embed-text@768" and len(vec) == 768
