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
   - Registration is `invite_only` by default and invites are created by an administrator, so for the first account set `SERVICE_REGISTRATION=open` in `.env` and run `docker compose up -d`.
   - Go to http://localhost:3000 (the port published by `docker-compose.yml`, or your chosen host/port) and **Register** your account.
   - Once registered, promote yourself to superuser to access the admin panel (then set `SERVICE_REGISTRATION=invite_only` again unless you want public sign-up):
     ```bash
     docker compose exec ivdrive-api env PYTHONPATH=/app python -m app.scripts.promote_user --email your@email.com
     ```

6. **Open the app**
   - Add your vehicle with your Škoda Connect credentials.
   - Access the Admin Dashboard via the sidebar (if promoted).

## Services

| Service | Purpose |
|---------|---------|
| **ivdrive-web** | Next.js frontend (port 3000 inside the container; `docker-compose.yml` publishes it as 3000, map it to any port you like). |
| **ivdrive-api** | FastAPI backend (port 8000). |
| **ivdrive-collector** | Background worker that polls the Škoda API and stores telemetry. |
| **postgres** | PostgreSQL database. |
| **valkey** | Valkey (Redis-compatible) cache. |

## Optional settings

- **CORS_ORIGINS** — If you access the UI from another origin (e.g. a different domain), add it here (JSON array of allowed origins).
- **NEXT_PUBLIC_API_URL** — Leave empty if the browser talks to the same host (recommended). Set only if the API is on a different host than the frontend; then rebuild the web image after changing.
- **LOG_LEVEL** — `info` (default) or `debug`.
- **COLLECTOR_DEBUG** — Set to `true` to log parsed API response summaries in the collector (for troubleshooting).

### ABRP Telemetry (optional)

iVDrive can push live vehicle data (SOC, charging status/power, position, range, odometer) to [A Better Route Planner](https://abetterrouteplanner.com) so ABRP can use it for live route planning. **Off by default.**

Each user configures their own free ABRP credentials in the UI (stored encrypted):

1. **API key** — generate a free Telemetry API key in your ABRP account under [Manage telemetry API keys](https://abetterrouteplanner.com/resources/api).
2. **Car token** — one per vehicle, from the ABRP app (Live Data → Custom connection).

Then in iVDrive: **Settings → Integrations — ABRP**, save the API key once, and paste each vehicle's car token with sync enabled. No server-side ABRP configuration is required.

**Limitation:** ABRP Custom connections only expose Driving and Charging data. Remote vehicle control from ABRP ("Remote data") is not supported — that is an ABRP-side limitation of the Telemetry API, not an iVDrive gap.

## Backups

- Back up the PostgreSQL data volume (`pgdata`) and your `.env` (especially `JWT_SECRET_KEY` and `ENCRYPTION_KEY`). Restore with the same keys so existing tokens and encrypted credentials remain valid.

For architecture and code layout, see [Project overview](project_overview.md).

## Upgrading

1. Read the release notes: some releases need an extra step, and v1.4.0 logs everyone out once.
2. Back up the database.
3. Run `docker compose exec ivdrive-api env PYTHONPATH=/app alembic upgrade head`, **then** start the new containers. (The API and collector repair a few additive schema changes by themselves if the migration is late, but the migration is the supported path.)

## Assistant database role

The assistant's custom-SQL tool runs as a restricted database role (`ivdrive_ai_readonly`) that can read only the analytical tables, with row-level security that limits every row to the signed-in user. That role and its policies are created by Alembic migrations. The fresh-install route above (`init_db`, then `alembic stamp head`) records the migrations as applied **without running them**, so a fresh self-hosted install has no such role: the assistant's other tools work, and the custom-SQL tool is unavailable (it fails closed rather than falling back to broader access). An installation that has run the migrations, such as an upgraded one, has the role.

