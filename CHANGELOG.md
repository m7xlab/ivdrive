# Changelog

## [Unreleased] - 2026-05-05
### Fixed
- HVACCostCard: Wrap `representative_temp_celsius` with `Number()` before `toFixed()` — defensive fix against string concatenation (e.g. "5"+"10"="510°C") if backend returns unexpected type.
- BatterySoHDashboard: Battery SoH tab with derived SoH from charging sessions + Skoda BMS comparison + degradation curve (via `battery-health` endpoint).

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