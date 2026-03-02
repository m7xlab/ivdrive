# Self-hosting iVDrive

This guide is for running the full iVDrive stack (API, collector, frontend, database, cache) on your own machine or NAS with Docker Compose. Most users can simply use [ivdrive.eu](https://ivdrive.eu) with no setup.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)

## Quick start

1. **Clone the repository**
   ```bash
   git clone https://github.com/m7xlab/iVDrive.git
   cd iVDrive
   ```

2. **Configure environment**
   - Create the local data directories:
     ```bash
     mkdir -p data/postgresql data/valkeydata
     ```
   - Copy `.env.example` to `.env`.
   - Set the required variables:
     - `POSTGRES_PASSWORD` — Database password.
     - `VALKEY_PASSWORD` — Cache password.
     - `JWT_SECRET_KEY` — A long random string (e.g. 64 characters) for signing tokens.
     - `ENCRYPTION_KEY` — Base64-encoded 32-byte key for encrypting stored credentials (e.g. Škoda Connect passwords).
   - See [.env.example](../.env.example) for all options and notes.

3. **Start the stack**
   ```bash
   docker compose up -d
   ```

4. **Initialize Database**
   Ensure the database and tables are created correctly:
   ```bash
   docker compose exec ivdrive-api env PYTHONPATH=/app python -m app.scripts.init_db
   docker compose exec ivdrive-api env PYTHONPATH=/app alembic stamp head
   ```

5. **Register & Promote Admin User**
   - Go to http://localhost:3035 (or your chosen host/port) and **Register** your account.
   - Once registered, promote yourself to superuser to access the admin panel:
     ```bash
     docker compose exec ivdrive-api env PYTHONPATH=/app python -m app.scripts.promote_user --email your@email.com
     ```

6. **Open the app**
   - Add your vehicle with your Škoda Connect credentials.
   - Access the Admin Dashboard via the sidebar (if promoted).

## Services

| Service | Purpose |
|---------|---------|
| **ivdrive-web** | Next.js frontend (port 3000 inside container; map to 3035 or your choice). |
| **ivdrive-api** | FastAPI backend (port 8000). |
| **ivdrive-collector** | Background worker that polls the Škoda API and stores telemetry. |
| **postgres** | PostgreSQL database. |
| **valkey** | Valkey (Redis-compatible) cache. |

## Optional settings

- **CORS_ORIGINS** — If you access the UI from another origin (e.g. a different domain), add it here (JSON array of allowed origins).
- **NEXT_PUBLIC_API_URL** — Leave empty if the browser talks to the same host (recommended). Set only if the API is on a different host than the frontend; then rebuild the web image after changing.
- **LOG_LEVEL** — `info` (default) or `debug`.
- **COLLECTOR_DEBUG** — Set to `true` to log parsed API response summaries in the collector (for troubleshooting).

## Backups

- Back up the PostgreSQL data volume (`pgdata`) and your `.env` (especially `JWT_SECRET_KEY` and `ENCRYPTION_KEY`). Restore with the same keys so existing tokens and encrypted credentials remain valid.

For architecture and code layout, see [Project overview](project_overview.md).
