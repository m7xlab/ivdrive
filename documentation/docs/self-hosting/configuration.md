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

`GEMINI_API_KEY`, `MINIMAX_API_KEY`, `EMBEDDING_*` — enable coach / embedding features where configured.

## Storage (optional)

GCS / S3 buckets for exports and conversation sessions if used.

## Frontend extras

`NEXT_PUBLIC_CARTO_BASEMAPS_API_KEY` — map tiles.  
`SITE_ANALYTICS_URL` / `SITE_ANALYTICS_KEY` — privacy-friendly analytics.
