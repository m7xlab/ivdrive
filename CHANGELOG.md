# Changelog

## [Unreleased] - 2026-05-08
### Fixed
- vehicles.py (`/statistics` endpoint): Timezone-aware day truncation using vehicle home_tz field — supports all IANA timezones; falls back to Europe/Vilnius for vehicles without home_tz set. Eliminates UTC midnight misalignment that caused Driving Stats historical data to show only 2 days instead of the full selected period.
- MovementDashboard (frontend): Use geofenceId instead of label string-matching to group Top Places — same Work geofence visits now merge into a single entry regardless of cluster centroid drift. Charging flag also merged correctly when multiple stays combine.
- analytics.py (`get_efficiency_curve`): Filter temperature buckets with `data_points < 3` — only buckets with ≥3 trips are returned, preventing unrealistic averages (~3.6 kWh/100km) from single-trip samples.
- analytics.py (`get_hvac_isolation`): Return specific diagnostic summary when no metrics calculable — explains which trip type is missing (cold vs optimal) and what date range is needed.
- Security: `vehicle.home_tz` validated against a whitelist of ~60 known-good IANA timezone strings before use in SQL `AT TIME ZONE` clause; `GROUP BY` / `ORDER BY` reference SELECT alias "period" instead of repeating f-string expressions.

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