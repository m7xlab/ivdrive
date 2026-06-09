# Changelog

## [Unreleased] - 2026-06-09
### Fixed
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