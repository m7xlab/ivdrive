---
sidebar_position: 2
title: Docker Compose
---

# Docker Compose

Standard self-host path.

## 1. Clone

```bash
git clone https://github.com/m7xlab/iVDrive.git
cd iVDrive
```

## 2. Environment

```bash
cp .env.example .env
```

Set at least:

| Variable | Purpose |
|----------|---------|
| `POSTGRES_PASSWORD` | Database password |
| `VALKEY_PASSWORD` | Cache password |
| `JWT_SECRET_KEY` | Auth token signing |
| `ENCRYPTION_KEY` | Encrypts vehicle credentials |

See [Configuration](./configuration.md) for the full list.

## 3. Start

```bash
mkdir -p data/postgresql data/valkeydata
docker compose up -d
```

| Service | Default URL |
|---------|-------------|
| Web UI | http://localhost:3000 |
| API | http://localhost:8000 |

## 4. Initialise the database

```bash
docker compose exec ivdrive-api env PYTHONPATH=/app python -m app.scripts.init_db
docker compose exec ivdrive-api env PYTHONPATH=/app alembic stamp head
```

## 5. Create an admin

1. Register in the UI (or via API)
2. Promote the user:

```bash
docker compose exec ivdrive-api env PYTHONPATH=/app python -m app.scripts.promote_user --email you@example.com
```

## 6. Add a vehicle

Sign in → **Add vehicle** → Škoda Connect credentials.

## Useful commands

```bash
docker compose logs -f ivdrive-api
docker compose logs -f ivdrive-collector
docker compose restart
docker compose down
```

## Optional landing

Production marketing + reverse proxy: [Landing proxy](./landing-proxy.md).
