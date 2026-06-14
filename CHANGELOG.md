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
- DrivingDashboard + MovementDashboard (frontend): All data sources now respect the selected dateRange — odometer, visited locations, time budget, and trips all use the same period filter. Previously time budget and mileage showed all-time data regardless of the date picker.
- DrivingDashboard (frontend): KPI cards now show period totals (sum of all days in range) instead of only the latest-day values. Historical stats table now shows all available rows with scrollable overflow instead of hard-coded slice of 7.
- analytics.py (`movement-stats`): Made `from_date`/`to_date` query params optional — when absent, returns all-time aggregation. Previously called `/time-budget` endpoint which had no date filter support.
- MovementDashboard (frontend): Time Budget now fetches period-filtered data instead of all-time. Badge updated from "All-time" to "Period".

### Fixed
- vehicles.py (`/statistics` endpoint): Timezone-aware day truncation using vehicle.home_tz field — supports all IANA timezones; falls back to Europe/Vilnius for vehicles without home_tz set. Eliminates UTC midnight misalignment that caused Driving Stats historical data to show only 2 days instead of the full selected period. **Security**: Uses SQLAlchemy `.op("AT TIME ZONE")(tz)` instead of `text(f"... '{tz}' ...")` — tz validated against IANA whitelist before reaching SQL.
- MovementDashboard (frontend): Use geofenceId instead of label string-matching to group Top Places — same Work geofence visits now merge into a single entry regardless of cluster centroid drift. Duration-weighted centroid averaging applied for coordinate-keyed (non-geofence) stays; geofence stays keep original center coordinates.
- analytics.py (`get_efficiency_curve`): Filter temperature buckets with `data_points < 3` — only buckets with ≥3 trips are returned, preventing unrealistic averages (~3.6 kWh/100km) from single-trip samples.
- analytics.py (`get_hvac_isolation`): Return specific diagnostic summary when no metrics calculable — explains which trip type is missing (cold vs optimal) and what date range is needed.
- Security: `vehicle.home_tz` validated against a whitelist of ~60 known-good IANA timezone strings before use in SQL; `GROUP BY` / `ORDER BY` reference SELECT alias "period" instead of repeating f-string expressions.

## [v1.0.23] - 2026-05-04
### Fixed
- collector.py: Replace `status_resp.overall.battery` attribute access with `getattr(..., 'battery', None)` — `VehicleStatusOverall` pydantic model has no `battery` field, causing `AttributeError` on every vehicle collection and blocking ALL data ingestion since ~May 5.
- HVACCostCard: Ensure `representative_temp_celsius` is numeric before `toFixed()` — defensive fix against string concatenation (e.g. "5"+"10"="510°C").
- security-scan.yml: Update Trivy action from v0.36.0 to v0.49.1; remove separate DB download step (v0.49.1 handles DB init automatically); exit-code 0 (report-only); remove SEMGREP_APP_TOKEN.

### Fixed
- ChargingEconomicsDashboard: Remove duplicate Recent Sessions Table block (same table was rendered twice).
- CarOverviewDashboard: Switch `Promise.all` → `Promise.all` → `Promise.allSettled` — if 1-2 of 15 parallel API requests fail, dashboard still renders partial data.
- StatisticsShell: Guard ArrowLeft/ArrowRight keyboard navigation against `input`/`textarea` elements (accessibility).
- settings/page.tsx: Fix `displayVal` to preserve explicit `0` values (was treating `0` as falsy).
- security-scan.yml: Scope Trivy scans to `./backend` directory only.
- MovementDashboard: Top Places React key changed from GPS coords to `place.label` — avoids key collision risk.
- MovementDashboard: Top Places GPS display increased from 4 → 5 decimal places (~1m precision).
- ChargingCurveIntegralsV2: `total_energy` sum rounded to 2 decimal places — eliminates `29.130000000000003 kWh` float artifact.
- SpeedTempMatrixDashboard: ErrorBoundary prevents blank panels; removed all `console.error` calls.
- `_get_nearest_elevation`: Fixed `text()` SQL expression — proper bound parameters for elevation cache.
- Elevation Penalty endpoint: Returns "Not enough trips with elevation data for analysis" when all trips lack elevation.
- HVAC Cost Summary: Track actual temperature band instead of hardcoding "10-20°C".
- alembic: merged vehicle_positions index branches resolving multiple-heads migration conflict.

## [v1.0.22] - 2026-04-22
### Added
- Advanced Statistics: TripsDashboard, MovementDashboard, DrivingStatisticsDashboard, ChargingStatisticsDashboard, MileageKMDashboard, ChargingCurveDashboard, HVACCostCard, ChargingCurveIntegralsDashboard, ElevationPenaltyDashboard, SpeedTempMatrixDashboard, IceTcoDashboard, RouteEfficiencyDashboard, PredictiveSocDashboard.
- Analytics engine: efficiency calibration, vampire drain analysis, battery health, charging economics, route efficiency.
- Geofencing: home/work geofence locations, distance calculations, location caching.
- Settings: per-vehicle efficiency calibration, collector configuration.

### Fixed
- ChargingCurveDashboard: API response mismatch fixed.
- TripsDashboard: React.Fragment replaced with `<>` shorthand.
- Winter Penalty: useId() for SVG gradient to avoid hydration mismatch (React #310).
- ChargingCurveIntegralsV2: brackets query no longer ignores date filters.
- Statistics: Energy Used now shows correct values for days with charging during parked periods.
- TripElevationCard: matches actual API response shape.
- `_store_trip_end`: selects oldest trip; Query bounds added on limit params.

## [v1.0.21] - 2026-04-14
### Added
- Battery Health endpoint and BatterySoHDashboard with derived SoH from charging sessions.
- Charging Economics dashboard with AC/DC split, cost trends, session details.

### Fixed
- P1 triage: elevation-stats endpoint, hvac-cost pagination, elevation-penalty N+1 queries.
- Arrival SOC calculation and charging wasted% denominator.
- Elevation cache LRU cap + ChargingCurveDashboard apiFetch fix.

## [v1.0.20] - 2026-04-10
### Added
- RouteEfficiencyDashboard with street-name reverse geocoding.
- PredictiveSocDashboard for arrival SoC prediction.

### Fixed
- SpeedTempMatrixDashboard: getColor null guard, max===min cap, ErrorBoundary.
- CarOverviewDashboard: Vampire drain rate display precision.
- MovementDashboard: GPS coordinates 5 decimal places in Top Places.

## [v1.0.19] - 2026-04-07
### Added
- ICE vs EV TCO comparison dashboard.
- Battery SoH degradation curve with Skoda BMS comparison.

## [v1.0.18] - 2026-04-05
### Added
- ChargingCurveIntegralsDashboard with SoC bracket analysis and wasted time callout.
- HVAC Power Isolation dashboard.

### Fixed
- ChargingeCurveIntegralsV2: session_id filter now works correctly with date filters.
- _store_trip_end selects oldest trip correctly; Query bounds prevent unbounded results.

## [v1.0.17] - 2026-04-03
### Added
- SpeedTempMatrixDashboard — speed × temperature consumption heatmap.
- ElevationPenaltyDashboard — elevation impact on efficiency.

### Fixed
- N+1 elevation queries → asyncio.gather for concurrent lookups.
- ErrorBoundary + console.error gating in SpeedTempMatrixDashboard.
- Elevation stats schema and response_model.

## [v1.0.16] - 2026-04-01
### Added
- StatisticsShell: tab consolidation (Charging Analysis, Driving Summary).
- ChargingAnalysis tab: merged ChargingCurve + ChargingCurveIntegrals.
- DrivingSummaryDashboard: Trips + Movement + DrivingStats + Mileage merged.

### Fixed
- TripsDashboard: Polyline onClick to eventHandlers (Leaflet v5 compat).
- StatisticsShell: restore missing ChargingStatisticsDashboard import.
- Route Efficiency + Predictive SoC tabs restored.

## [v1.0.15] - 2026-03-28
### Added
- CarOverviewDashboard: Live Pulse hero + Winter Penalty + Vampire Drain.
- MovementDashboard: visited locations map, activity timeline, geofences, time budget.

### Fixed
- Odometer readings without date filter for mileage trend.
- All-time data in MovementDashboard.

## [v1.0.14] - 2026-03-26
### Added
- ChargingEconomicsDashboard: sessions, energy, cost, AC/DC split, trend chart.
- Route efficiency and predictive SoC tabs.

### Fixed
- Next.js 15 compatibility: next.config.js, eslint ignore.
- Auth context: add is_totp_enabled to User interface.
- StatisticsShell: replace charging-stats+analysis with charging-economics.

## [v1.0.13] - 2026-03-24
### Added
- Statistics page: full tab navigation with CarOverview, Trips, Movement, Driving Stats, Charging Stats, Charging Curve, HVAC Isolation, Charging Curve Integrals, Elevation Penalty, Speed × Temp, ICE vs EV, Route Efficiency, Arrival SoC, Mileage, Battery SoH.

### Fixed
- Per-vehicle inline Efficiency Calibration in vehicle card settings.
- Skoda OAuth defaults restored, no blocking validator.

## [v1.0.12] - 2026-03-22
### Added
- Advanced Statistics backend endpoints: efficiency, vampire drain, battery health, charging economics, route efficiency, predictive soc, speed-temp-matrix, elevation penalty.

### Fixed
- DisplayVal NaN guard and collector-auth error message.

## [v1.0.11] - 2026-03-20
### Added
- Vehicle status overview: battery, range, charging, climatization state bands.
- WLTP range endpoint and display.

## [v1.0.10] - 2026-03-18
### Added
- Trip telemetry: full trip tracking with odometer, battery, position, temperature, HVAC state.
- Drive level data with speed, acceleration, deceleration, elevation.

## [v1.0.9] - 2026-03-15
### Added
- Charging session tracking: plug-in/out events, charge rate, energy, duration.
- Charging curve recording: SoC, power, temperature over time.

## [v1.0.8] - 2026-03-12
### Added
- Geocoded locations cache for reverse geocoding.
- Elevation data integration with OpenTopoData.

## [v1.0.7] - 2026-03-10
### Added
- Collector: full MySkoda API integration for Enyaq/iV vehicles.
- OAuth token management with encrypted storage.
- Background scheduler for periodic data collection.

## [v1.0.6] - 2026-03-07
### Added
- User settings: calibration, geofences, notifications.
- User vehicle management with VIN registration.

## [v1.0.5] - 2026-03-05
### Added
- Authentication: JWT + TOTP 2FA support.
- User management and session handling.

## [v1.0.4] - 2026-03-03
### Added
- Database: PostgreSQL with Alembic migrations.
- API v1 endpoints: vehicles, trips, charging, analytics.

## [v1.0.3] - 2026-03-01
### Added
- Frontend: Next.js 15 dashboard with Tailwind CSS.
- Dark/light theme support.

## [v1.0.2] - 2026-02-28
### Added
- Docker Compose setup: backend, frontend, postgres, valkey.

## [v1.0.1] - 2026-02-26
### Added
- Project skeleton: FastAPI backend, Next.js frontend.
- GitHub Actions CI/CD with security scanning.

## [v1.0.0] - 2026-02-24
### Added
- Initial release: iVDrive — Škoda API vehicle statistics platform.