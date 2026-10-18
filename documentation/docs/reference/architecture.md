---
sidebar_position: 1
title: Architecture
---

# Architecture

iVDrive is a multi-container Docker system.

## Components

| Component | Technology | Role |
|-----------|------------|------|
| **Web UI** | Next.js (React, Tailwind) | Dashboard, statistics, settings |
| **API** | FastAPI + SQLAlchemy + Alembic | Auth, vehicle commands, queries |
| **Collector** | Python worker | Polls Škoda Connect, stores telemetry |
| **Database** | PostgreSQL (+ pgvector) | Users, vehicles, history |
| **Cache** | Valkey | State, cache, pub/sub |
| **Landing** *(optional)* | Static Next + Caddy | Marketing + reverse proxy |

## Request flow (same-origin)

```
Browser → Web (Next.js) → /api/* proxy → FastAPI
                              ↓
                         PostgreSQL / Valkey
                              ↑
                         Collector → Škoda Connect API
```

## Security model

- JWT access + refresh tokens in **HttpOnly cookies**
- CSRF protection where applicable
- Vehicle credentials encrypted with `ENCRYPTION_KEY`
- Per-user data isolation (RLS where configured)
- Security headers / CSP on the web app

## Data model (high level)

- **Users** — accounts, settings, 2FA
- **User vehicles** — Connect-linked cars
- **Trips / charging sessions / positions / battery** — telemetry history
- **Derived analytics** — SoH estimates, penalties, cost views

## Extending

See [Contributing](../community/contributing.md) for local development setup and the REST API surface exposed under `/api`.
