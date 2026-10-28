"""Pluggable LLM providers for the AI assistant.

Everything is optional and driven by environment variables; a provider that is
not configured simply does not exist (no Gemini key -> no Gemini).

  OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL        any OpenAI-compatible server
  ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL / ANTHROPIC_MODEL   Anthropic (or compatible proxy)
  OLLAMA_BASE_URL / OLLAMA_MODEL                          local models, no key needed
  GEMINI_API_KEY / GEMINI_BASE_URL / GEMINI_MODEL         optional
  MINIMAX_API_KEY / MINIMAX_BASE_URL / MINIMAX_MODEL      optional
  LLM_TIMEOUT_SECONDS (default 60), LLM_FALLBACK_PROVIDERS (comma list, "none" disables)

OPENAI_BASE_URL alone (no key) is enough for LM Studio / vLLM / llama.cpp servers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import httpx

_PLACEHOLDERS = {"", "change_me", "changeme", "your_key_here"}


def _env(name: str) -> str:
    v = os.getenv(name, "").strip()
    return "" if v.lower() in _PLACEHOLDERS else v


@dataclass(frozen=True)
class Provider:
    name: str
    kind: str          # "openai" | "anthropic" | "gemini"
    base_url: str
    api_key: str
    default_model: str


@dataclass
class LLMResult:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0


class LLMError(Exception):
    pass


def _trim(url: str) -> str:
    return url.rstrip("/")


def configured_providers() -> dict[str, Provider]:
    """Providers enabled by the current environment, in default fallback order."""
    out: dict[str, Provider] = {}

    if _env("OPENAI_API_KEY") or _env("OPENAI_BASE_URL"):
        out["openai"] = Provider(
            "openai", "openai", _trim(_env("OPENAI_BASE_URL") or "https://api.openai.com/v1"),
            _env("OPENAI_API_KEY"), _env("OPENAI_MODEL") or "gpt-4o-mini",
        )
    if _env("ANTHROPIC_API_KEY") or _env("ANTHROPIC_BASE_URL"):
        out["anthropic"] = Provider(
            "anthropic", "anthropic", _trim(_env("ANTHROPIC_BASE_URL") or "https://api.anthropic.com"),
            _env("ANTHROPIC_API_KEY"), _env("ANTHROPIC_MODEL") or "claude-haiku-5-5",
        )
    if _env("OLLAMA_BASE_URL"):
        base = _trim(_env("OLLAMA_BASE_URL"))
        if not base.endswith("/v1"):
            base += "/v1"
        out["ollama"] = Provider("ollama", "openai", base, _env("OLLAMA_API_KEY"), _env("OLLAMA_MODEL") or "llama3.1")
    if _env("MINIMAX_API_KEY"):
        out["minimax"] = Provider(
            "minimax", "openai", _trim(_env("MINIMAX_BASE_URL") or "https://api.minimax.io/v1"),
            _env("MINIMAX_API_KEY"), _env("MINIMAX_MODEL") or "MiniMax-M3",
        )
    if _env("GEMINI_API_KEY"):
        out["gemini"] = Provider(
            "gemini", "gemini", _trim(_env("GEMINI_BASE_URL") or "https://generativelanguage.googleapis.com/v1beta"),
            _env("GEMINI_API_KEY"), _env("GEMINI_MODEL") or "gemini-2.5-flash",
        )
    return out


def provider_order(requested: str | None) -> list[Provider]:
    """Requested provider first (if configured), then the configured fallbacks."""
    avail = configured_providers()
    order: list[str] = []
    if requested and requested in avail:
        order.append(requested)
    fb = _env("LLM_FALLBACK_PROVIDERS").lower()
    if fb != "none":
        extra = [p.strip() for p in fb.split(",") if p.strip()] if fb else list(avail)
        order += [p for p in extra if p in avail and p not in order]
    return [avail[n] for n in order]


def timeout_seconds() -> float:
    try:
        return float(_env("LLM_TIMEOUT_SECONDS") or 60)
    except ValueError:
        return 60.0


def _err(name: str, resp: httpx.Response) -> LLMError:
    return LLMError(f"{name} HTTP {resp.status_code}: {resp.text[:100]}")


async def complete(
    provider: Provider, model: str, system: str, user: str, *,
    temperature: float = 0.3, client: httpx.AsyncClient | None = None,
) -> LLMResult:
    """One non-streaming completion. Raises LLMError on any failure."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=timeout_seconds())
    try:
        if provider.kind == "openai":
            headers = {"Content-Type": "application/json"}
            if provider.api_key:
                headers["Authorization"] = f"Bearer {provider.api_key}"
            resp = await client.post(
                f"{provider.base_url}/chat/completions", headers=headers,
                json={"model": model, "temperature": temperature,
                      "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            )
            if resp.status_code != 200:
                raise _err(provider.name, resp)
            data = resp.json()
            u = data.get("usage") or {}
            cached = u.get("cached_tokens") or (u.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
            return LLMResult(
                data["choices"][0]["message"]["content"] or "",
                u.get("prompt_tokens", 0), u.get("completion_tokens", 0), cached,
            )

        if provider.kind == "anthropic":
            base = provider.base_url
            url = f"{base}/messages" if base.endswith("/v1") else f"{base}/v1/messages"
            headers = {"Content-Type": "application/json", "anthropic-version": "2023-06-01"}
            if provider.api_key:
                headers["x-api-key"] = provider.api_key
            resp = await client.post(url, headers=headers, json={
                "model": model, "max_tokens": 4096, "temperature": temperature,
                "system": system, "messages": [{"role": "user", "content": user}],
            })
            if resp.status_code != 200:
                raise _err(provider.name, resp)
            data = resp.json()
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
            u = data.get("usage") or {}
            return LLMResult(
                text, u.get("input_tokens", 0), u.get("output_tokens", 0), u.get("cache_read_input_tokens", 0),
            )

        if provider.kind == "gemini":
            resp = await client.post(
                f"{provider.base_url}/models/{model}:generateContent",
                headers={"Content-Type": "application/json", "x-goog-api-key": provider.api_key},
                json={"contents": [{"parts": [{"text": user}]}],
                      "systemInstruction": {"parts": [{"text": system}]}},
            )
            if resp.status_code != 200:
                raise _err(provider.name, resp)
            data = resp.json()
            u = data.get("usageMetadata") or {}
            return LLMResult(
                data["candidates"][0]["content"]["parts"][0]["text"],
                u.get("promptTokenCount", 0), u.get("candidatesTokenCount", 0), u.get("cachedContentTokenCount", 0),
            )
        raise LLMError(f"unknown provider kind {provider.kind}")
    except LLMError:
        raise
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        raise LLMError(f"{provider.name} {type(e).__name__}: {str(e)[:80]}") from e
    finally:
        if own:
            await client.aclose()
