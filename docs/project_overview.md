# iVDrive — Project Overview & Architecture

This document describes the technical architecture of iVDrive for contributors and anyone running or extending the stack. Most users can simply [use iVDrive online](https://ivdrive.eu); self-hosting is documented in [Self-hosting](self-hosting.md).

---

## Project description

**iVDrive** is a premium electric vehicle data monitoring application for Volkswagen Group EVs, starting with Škoda. It collects telemetry (battery, range, location, drives, charging sessions, trips) and provides a single web dashboard to view and analyze your data. You can use it at [ivdrive.eu](https://ivdrive.eu) with no setup, or self-host the full stack with Docker.

---

## Technology stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Frontend** | Next.js (React, App Router), Tailwind CSS, Recharts, React-Leaflet, Lucide React | Web UI, charts, maps |
| **Backend** | Python 3.12+, FastAPI, SQLAlchemy (async), Alembic, Pydantic, NumPy, PyJWT | REST API, auth, validation, JWT |
| **Database** | PostgreSQL (asyncpg) | Users, vehicles, telemetry history |
| **Cache** | Valkey (Redis-compatible) | State, cache, pub/sub |
| **Infrastructure** | Docker & Docker Compose | Multi-container deployment |

---

## High-level architecture

iVDrive runs as a multi-container Docker environment defined in `docker-compose.yml`:

| Service | Role |
|---------|------|
| **ivdrive-web** | Next.js frontend (port 3000). Proxies `/api/*` to the backend so the app can be served from a single origin (e.g. ivdrive.eu). |
| **ivdrive-api** | FastAPI backend (port 8000). REST API, JWT auth, vehicle commands, statistics. |
| **ivdrive-collector** | Background worker. Polls the Škoda API for connected vehicles, decrypts stored credentials, fetches and parses telemetry, writes to PostgreSQL. |
| **postgres** | PostgreSQL database. Users, vehicles, and all historical telemetry. |
| **valkey** | Valkey (Redis-compatible). State, caching, and optional pub/sub for live updates. |

---

## Directory structure

```text
iVDrive/
├── docker-compose.yml       # Multi-container setup
├── .env                     # Environment variables (not committed; see .env.example)
├── frontend/                # Next.js application
│   ├── next.config.ts       # API proxy/rewrite rules
│   ├── src/
│   │   ├── app/             # App Router
│   │   │   ├── (auth)/      # Login / Register
│   │   │   ├── (dashboard)/ # Dashboard, vehicles list
│   │   │   │   └── vehicles/[id]/  # Vehicle detail & Statistics
│   │   ├── components/     # Shared UI components (maps, charts, layout)
│   │   └── lib/             # API client (api.ts), utilities
│   └── package.json
└── backend/                 # FastAPI + collector
    ├── alembic.ini          # Database migrations
    ├── requirements.txt
    └── app/
        ├── main.py          # FastAPI app entry
        ├── api/v1/          # REST routes (auth, vehicles, statistics, settings, commands)
        ├── models/          # SQLAlchemy models (user, vehicle, telemetry)
        ├── schemas/         # Pydantic schemas
        ├── services/        # collector, skoda_api, crypto, events
        └── migrations/      # Alembic migration scripts
```

---

## Database schema (overview)

The database is relational and tuned for time-series and aggregated statistics.

| Area | Tables / concepts |
|------|-------------------|
| **Users & auth** | `users` |
| **Vehicles** | `user_vehicles` (metadata, VIN hash, encrypted Škoda Connect credentials) |
| **Geofences** | `geofences` (user-defined areas) |
| **Point-in-time telemetry** | `vehicle_positions`, `vehicle_states`, `air_conditioning_states`, `connection_states`, `maintenance_reports` |
| **Aggregated / events** | `locations`, `trips`, `charging_stations`, `charging_sessions`, `drives` (with `drive_levels`, `drive_ranges`) |

---

## Key mechanisms

- **Collector** — Runs in a loop: loads active vehicles, decrypts credentials with `ENCRYPTION_KEY`, calls the Škoda API, parses responses, and writes to PostgreSQL. Detects state changes (e.g. trip start/end, charging session) and creates or updates records accordingly.
- **Frontend proxy** — Next.js rewrites `/api/*` to the backend container (`ivdrive-api:8000`), so the browser uses a single origin and CORS is avoided.
- **Statistics API** — Backend aggregates by day/week/month (e.g. `date_trunc`, `sum`) for the dashboard. Mileage forecasting uses simple regression on historical odometer data.
- **Maps** — Frontend uses React-Leaflet with OpenStreetMap/CartoDB for visited locations and live position.

---

## For contributors and AI agents

When modifying the codebase:

1. **Frontend API calls** — Use relative paths (e.g. `/api/v1/vehicles`) so the Next.js proxy works.
2. **Database models** — After changing `backend/app/models/`, add an Alembic migration, e.g.  
   `docker compose exec ivdrive-api alembic revision --autogenerate -m "description"`  
   then review the generated migration.
3. **Collector** — Shares the same models as the API. Logs: `docker compose logs ivdrive-collector` (or your container name).
4. **New Python dependencies** — Add to `backend/requirements.txt`, then rebuild and restart the API and collector containers.

For full contribution workflow, see [CONTRIBUTING.md](../CONTRIBUTING.md).
