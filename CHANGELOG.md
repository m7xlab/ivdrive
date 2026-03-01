# Changelog

All notable changes to the iVDrive project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-03-01
### Added
- **Car Overview Dashboard**: Interactive Grafana-style UI featuring detailed line and area charts for battery levels, range, outside temperature, and efficiency.
- **Smart Polling Collector**: Rebuilt the background data collector. When the car is parked and asleep, API calls are reduced by 85% to preserve Skoda API limits. Active sessions auto-trigger high-frequency polling.
- **Flexible Date Picker**: Fully custom, Tailwind v4-styled DateRangePicker utilizing Tremor Raw and `react-day-picker`. Supports exact date spans and quick presets (Last 7 Days, Month, etc.).
- **Visited Dashboard**: An interactive Carto-styled map utilizing `react-leaflet`, mapping exact GPS coordinates and categorizing them as regular driving points or charging sessions.
- **Extended Analytics Engine**: Alembic schemas migrated to track 200+ specific telemetry points.
- **Security & Infrastructure**: Fully Dockerized with container namespace isolation (`ivprod`). Sensitive development configuration cleanly scrubbed from repository.
- **Charging Statistics**: Implemented complete charging cost parsing, session views, and Winter Penalty / Efficiency metrics based on `wltp_range_km` and `range_estimated_full`.

### Changed
- Replaced legacy rigid data queries to dynamically scale based on user date selections without truncating at 500 rows.
- Split UI components from raw Radix into beautifully styled Next.js native layouts, resolving dark/light mode mismatches.

### Fixed
- Fixed Skoda Authentication token refresh infinite loops.
- Resolved issue where identical sequential step-chart segments caused frontend memory ballooning. Backend now collapses continuous ranges accurately.
- Addressed Docker port conflicts that interfered with parallel deployments.

## [1.0.1] - 2026-03-01
### Fixed
- Disabled `pool_pre_ping` in `asyncpg` SQLAlchemy engine configuration to completely resolve an architectural bug causing `500 Internal Server Error (MissingGreenlet)` crashes when multiple users concurrently registered vehicles and initiated background API polling.
