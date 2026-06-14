# Changelog

## [v1.1.0] - 2026-06-14
Minor release: AI assistant goes production-grade — streamed chat answers,
admin-controlled RAG embedding backfill, and a safe production-restore migration
path. Plus a branded in-app dialog/toast system and a corrected production
compose template.

### Added
- **Streaming chat (SSE)**: new `POST /api/v1/chat/stream` endpoint streams answers as Server-Sent Events. It runs the existing RAG/agentic pipeline as a background task and emits `status` heartbeats every 2s so the connection never goes idle, then streams the answer as `delta` events and a final `done` event (session_id + sources). Fixes the proxy `ECONNRESET` ("Internal Server Error") on slow multi-turn follow-ups that chain several LLM calls (~20s+). Frontend chat widget now renders the answer as it streams.
- **Admin RAG embedding backfill**: new `GET /api/v1/admin/ai/embeddings/status` and `POST /api/v1/admin/ai/embeddings/backfill` (`mode=missing|all`). The Admin → AI Assistant panel gains a "RAG Embeddings" card with coverage/queue stats and **Backfill missing** / **Re-embed all** buttons. Backfill is enqueue-only (pure SQL into `ai_embeddings_queue`); the collector worker embeds asynchronously — no external API calls inside the request.
- **Branded feedback system** (`components/ui/feedback.tsx`): app-wide `useConfirm()` modal + `useToast()` notifications styled to the iVDrive design system, replacing all native `window.confirm()`/`alert()` popups in the admin pages and AI panel.

### Fixed
- **Production-restore migration path**: the `f4b2c3d4e5f6` bridge migration falsely assumed restored production DBs already had the AI/vector base (vector extension, `ai_embeddings` + chat tables, RLS, role). They don't — production never ran the AI feature — so `alembic upgrade head` failed at `8b3c4d5e6f71` (`TRUNCATE ai_embeddings` on a non-existent table). Added idempotent catch-up migration `f5a6b7c8d9e0` that recreates the full AI/vector base, inserted before the dependent migrations. Rehearsed end-to-end against a production restore: clean upgrade to head, schema identical to dev.
- **admin_ai.py `update_user_ai_access`**: editing one override field (e.g. `note`) wiped all other per-user overrides — the `ON CONFLICT DO UPDATE` overwrote unset columns with `NULL`. Now uses `COALESCE(EXCLUDED.x, existing)` to preserve untouched fields. (PR #149)
- **chat_tools.py `execute_read_only_sql`**: `Decimal` values from SQL aggregates (distance, energy, costs) crashed `json.dumps`, surfacing as `SQL_ERROR` for most analytical queries. Now coerced to `float`. (PR #149)
- **embedding_builders.py**: `build_charging_curve_summary` and `build_drive_consumption_summary` crashed (`TypeError: ... NoneType.__format__`) for vehicles whose curve/consumption columns are entirely NULL (AVG/MIN/MAX → None). Now formatted defensively (`n/a`).
- **IVDriveAIWidget.tsx**: chart parser regex `json_chart\n` → `json_chart\s*` so charts render even without a leading newline; chat input textarea now auto-grows up to `max-h-32` instead of being pinned at 44px. (PR #149)
- **ChargingAnalysisDashboard.tsx**: fixed a committed syntax error (an `import` statement pasted inside another multi-line `import {}` block) that broke the production build regardless of `ignoreBuildErrors`.

### Changed
- **Production compose** (`docker-files/compose.yml`): `postgres:18` → `pgvector/pgvector:pg18` (required by the AI `CREATE EXTENSION vector` migration); added `MINIMAX_API_KEY`, `GEMINI_API_KEY`, S3/storage + `CONVERSATION_SESSIONS_BUCKET`, Škoda creds, `EMBEDDING_WORKER_*` (collector), `SITE_ANALYTICS_*` (web), and `env_file: .env`; default `IVDRIVE_VERSION` → `v1.1.0`.
- **Env templates** (`.env.example`, `backend/.env.example`): documented the AI, embedding-worker, S3, Škoda, and analytics variables.

### Database
- `f5a6b7c8d9e0_ai_base_catchup_for_production.py` — idempotent AI/vector base (extension, `ai_embeddings`/queue/chat tables, RLS policies, `ivdrive_ai_readonly` grants); `5c0a1b2c3d4e` re-pointed onto it. No-op on dev/fresh installs.

### Multi-turn RAG (folded in from this branch)
- **chat.py (multi-turn RAG regression)**: `route_intent_via_llm` was called WITHOUT `conversation_history`, so the agentic router had no way to resolve pronouns like "that", "it", "the last one", or "how much did that cost?" in follow-up questions. Result: router picked the wrong tool/args (often an empty `vehicle_name=""`) or fell back to `log_missing_capability` and the AI refused to answer. Fix:
  1. `route_intent_via_llm` now accepts `conversation_history` and `detected_vehicle_name`; both are injected into the router prompt as a "Previous conversation" block + vehicle hint.
  2. `chat.py` now resolves the vehicle name from the most recent assistant/user turn when the current message doesn't mention one (word-boundary match, case-insensitive).
  3. Both the initial router call AND the SQL-healing re-prompt loop now pass `conversation_history` so context survives across the 3-attempt retry.
- **chat_tools.py (missing table)**: `log_missing_capability` referenced `ai_missed_intents` table that was never created — caused `Internal Server Error` whenever the router fell back to "I don't have that capability". Added migration `8b3c4d5e6f70_add_ai_missed_intents.py` to create the table + index; applied to production DB.
- chat.py (agentic router): tighten prompt to forbid `log_missing_capability` for short follow-ups ("how much did that cost?") when prior turn established a vehicle — prefer tools 5/6/7 with the resolved vehicle name.

## [Unreleased] - 2026-05-08
### Fixed
- vehicles.py (`/statistics` endpoint): Use `AT TIME ZONE 'Europe/Vilnius'` for `date_trunc` on both trips and charging sessions — trips near local midnight were bucketed into wrong UTC day, causing Driving Stats historical data to show only 2 days instead of full May 1-8 period.
- MovementDashboard (frontend): Use geofence label as grouping key in Top Places instead of lat/lon grid — same Work geofence visits now merge into a single entry regardless of cluster centroid drift.
- analytics.py (`get_efficiency_curve`): Filter temperature buckets with `data_points < 3` — view was returning single-trip buckets producing unrealistic ~3.6 kWh/100km at 5°C.
- analytics.py (`get_hvac_isolation`): Return specific diagnostic summary when no metrics calculable (cold vs optimal trip types missing) instead of static generic message.

## [v1.0.23] - 2026-05-04
## [Unreleased] - 2026-05-07
### Fixed
- collector.py: Replace `status_resp.overall.battery` attribute access with `getattr(..., 'battery', None)` — `VehicleStatusOverall` pydantic model has no `battery` field, causing `AttributeError` on every vehicle collection and blocking ALL data ingestion since ~May 5. Also fixed duplicate reference at battery temperature extraction (line ~956).
- BatterySoHDashboard: Battery SoH tab with derived SoH from charging sessions + Skoda BMS comparison + degradation curve (via `battery-health` endpoint).
- security-scan.yml: Trivy DB pre-download step; exit-code changed to 0 (report-only, doesn't block merges); SEMGREP_APP_TOKEN removed (free CI mode with --disable-version-check).

### Fixed
- security-scan.yml: Update Trivy action from v0.36.0 to v0.49.1, remove separate DB download step (v0.49.1 handles DB init automatically). Fixes "Download Trivy vulnerability database" step failure blocking all workflow runs.
- ChargingEconomicsDashboard: Remove duplicate Recent Sessions Table block (copy-paste error — same table rendered twice).
- CarOverviewDashboard: Switch `Promise.all` → `Promise.allSettled` — if 1-2 of 15 parallel API requests fail, dashboard still renders partial data.
- StatisticsShell: Guard ArrowLeft/ArrowRight keyboard navigation against `input`/`textarea` elements (accessibility).
- settings/page.tsx: Fix `displayVal` to preserve explicit `0` values (was treating `0` as falsy).
- security-scan.yml: Scope Trivy image scan to `./backend` with `target:api`; scope Trivy filesystem scan to `./backend` (was scanning entire repo root).
- MovementDashboard: Top Places React key changed from GPS coords to `place.label` — avoids key collision risk for places within ~1m.
- MovementDashboard: Top Places GPS display increased from 4 → 5 decimal places (~1m precision).
- ChargingCurveIntegralsV2: `total_energy` sum rounded to 2 decimal places — eliminates float artifact like `29.130000000000003 kWh`.
- SpeedTempMatrixDashboard: Removed all `console.error` calls — ErrorBoundary handles errors silently in production.
- SpeedTempMatrixDashboard: ErrorBoundary prevents blank panels when chart rendering fails.
- `_get_nearest_elevation`: Fixed `text()` SQL expression — was using invalid SQLAlchemy usage causing elevation cache to always miss. Now uses proper bound parameters.
- Elevation Penalty endpoint: Returns "Not enough trips with elevation data for analysis" message when all trips lack elevation data.
- HVAC Cost Summary: Track actual temperature band instead of hardcoding "10-20°C"; show correct band in summary.
- alembic: merged vehicle_positions index branches (d1e2f3a4bb5c + a1b2c3d4e5f8) resolving multiple-heads migration conflict; production upgrade path now clean.

## [Unreleased] - 2026-05-01
### Added
- BatterySoHDashboard: Battery SoH tab with derived SoH from charging sessions + Skoda BMS comparison + degradation curve.

### Fixed
- MovementDashboard: Remove dead `formatDuration()` wrapper that divided by 60 before passing to `formatSmartDuration`, causing time values to display 60x smaller than actual.
- Migration 4c5c9e5b4a60: Remove destructive DROP TABLE/DROP INDEX ops that would have deleted 481 `geocoded_locations` rows and 516 `charging_sessions` rows. Now only adds calibration columns to `user_vehicles`.

## [Unreleased] - 2026-05-01
### Added
- BatterySoHDashboard: Battery SoH tab with derived SoH from charging sessions + Skoda BMS comparison + degradation curve.

### Fixed
- MovementDashboard: Remove dead formatDuration() wrapper that divided by 60 before passing to formatSmartDuration, causing time values to display 60x smaller than actual.
- Migration 4c5c9e5b4a60: Remove destructive DROP TABLE/DROP INDEX ops that would have deleted 481 geocoded_locations rows and 516 charging_sessions rows. Now only adds calibration columns to user_vehicles.

## [Unreleased] - 2026-04-30
### Fixed
- Charging Curve Integrals: `total_energy_kwh` display now rounded to 2 decimal places — eliminates `29.130000000000003 kWh` float artifact.
- ICE vs EV: Added proper spacing in savings line — `€ saved` and `€/kWh`, `€/L` instead of `€saved` and `0.3499€/kWh`.
- ICE vs EV: Rate values now display at 2 decimal precision max (was 4 decimals like `0.1955€/kWh`).
- Car Overview: Vampire drain rate display reduced from 4 to 2 decimal places on hourly rate.
- Movement Dashboard: GPS coordinates in Top Places now display 5 decimal places (~1m precision).
- SpeedTempMatrixDashboard: getColor null guard, max===min cap, ErrorBoundary, removed broken Tooltip formatter.
- Arrival SOC ~0%: arrival SOC calculation fixed, charging wasted% denominator fixed.
- Route Efficiency: GPS coordinates show 5 decimal places in tooltips.
- Elevation Penalty: use asyncio.gather for concurrent elevation lookups (2 round-trips instead of 2*N).

All notable changes to the iVDrive project will be documented in this file.