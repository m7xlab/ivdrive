---
sidebar_position: 3
title: Configuration
---

# Configuration

All runtime settings live in `.env` (copied from `.env.example`).

## Core secrets

| Variable | Notes |
|----------|-------|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Database |
| `VALKEY_PASSWORD` | Cache |
| `JWT_SECRET_KEY` | Long random string |
| `ENCRYPTION_KEY` | Used to encrypt Connect credentials |

:::warning
Back up secrets securely. Losing `ENCRYPTION_KEY` makes existing vehicle credentials unreadable.
:::

## Registration

| Variable | Values |
|----------|--------|
| `SERVICE_REGISTRATION` | `open` or `invite_only` |

## URLs

| Variable | Purpose |
|----------|---------|
| `APP_BASE_URL` | Public base URL used in emails/links |
| `NEXT_PUBLIC_API_URL` | Browser-facing API URL (often empty when using same-origin proxy) |
| `NEXT_PUBLIC_API_INTERNAL` | Docker-internal API (`http://ivdrive-api:8000`) |

## Email (SMTP)

`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` — for invites, verification and passports.

## Škoda Connect

`SKODA_BASE_URL`, `SKODA_AUTH_CLIENT_ID`, `SKODA_AUTH_REDIRECT_URI` — usually provided for the default deployment; advanced self-hosters may need their own client registration.

## AI (optional)

All providers are optional; only configured ones are used. Pick provider and model per tier in **Admin → AI Assistant**.

| Variable | Purpose |
|----------|---------|
| `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_MODEL` | Any OpenAI-compatible server (OpenAI, LM Studio, vLLM, OpenRouter, LiteLLM). Key optional for local servers. |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `ANTHROPIC_MODEL` | Anthropic, or a compatible proxy. |
| `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | Local models, no key. From Docker use `http://host.docker.internal:11434`. |
| `GEMINI_API_KEY`, `MINIMAX_API_KEY` | Optional hosted providers. |
| `LLM_TIMEOUT_SECONDS`, `LLM_FALLBACK_PROVIDERS` | Timeout (default 60) and fallback list (`none` disables fallback). |
| `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL` | RAG embeddings (768-dim). Unset = Gemini if its key is set, else an offline hash. `ollama` / `openai` use an OpenAI-compatible `/embeddings` endpoint. |

Free Google AI Studio keys work with `gemini-2.5-flash` (the seeded Pro/Team model).

## Storage (optional)

GCS / S3 buckets for exports and conversation sessions if used.

## Frontend extras

`NEXT_PUBLIC_CARTO_BASEMAPS_API_KEY` — map tiles.  
`SITE_ANALYTICS_URL` / `SITE_ANALYTICS_KEY` — privacy-friendly analytics.
