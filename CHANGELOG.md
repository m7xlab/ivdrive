# Changelog

All notable changes to the iVDrive project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.4] - 2026-03-02
### Added
- **Two-Factor Authentication (2FA)**: Implemented TOTP-based security (Google Authenticator, Authy).
- **QR Code Setup**: Native QR code generation in Settings for seamless 2FA activation.
- **Secure Login Flow**: Two-step authentication process with short-lived challenge tokens.
- **Enhanced Data Persistence**: New database initialization script (`init_db.py`) for fresh environment setups.

### Fixed
- **Managed Beta Documentation**: Updated README and docs to reflect current Invite-Only status and self-hosting best practices.
- **QR Rendering**: Fixed base64 Data URI formatting to ensure QR codes render correctly across all browsers.
- **Infrastructure**: Explicitly mapped `SERVICE_REGISTRATION` and SMTP environment variables in Docker Compose.

## [1.0.3] - 2026-03-02
### Added
- **Invite-Only Registration**: Implemented a "Request for Invite" system to prevent unauthorized signups.
- **Admin Dashboard**: New Tremor-based `/admin` panel for managing user invitations, approvals, and superuser promotions.
- **SMTP Integration**: Automated HTML invitation emails sent via Mailgun on approval.
- **Security**: Added `is_superuser` role to the User model and protected administrative endpoints with strict superuser-only dependencies.

### Fixed
- **Smart Polling v2.0**: Removed the redundant 30-minute "Full Refresh" logic. The system now utilizes a strict two-path telemetry fetch (Parked vs. Active) to minimize API hits and strictly respect Skoda rate limits.
- **App Configuration**: Updated `APP_BASE_URL` to `https://ivdrive.eu` to ensure correct registration links in emails.

## [1.0.2] - 2026-03-01
### Fixed
- **Smart Polling Loop**: Fixed a bug where the `_sync_vehicles_from_db` daemon would forcefully reset the APScheduler job to the "Parked" interval every 90 seconds, causing rapid API polling and ignoring the user's active/parked settings.
- **Ghost Car Records**: Wrapped the Skoda API authentication layer in a `try...except` block with `await db.rollback()`. This prevents orphaned "Ghost Car" records from saving to the database when invalid credentials or rate-limit throttles trigger a `500 Internal Server Error`.
- **False Active States**: Patched the `is_charging` logic to strictly check for the `CHARGING` state. The daemon will no longer classify the car as active (and poll every 5 minutes) simply because it is plugged in (`CONNECT_CABLE` or `READY_FOR_CHARGING`).
- **Silent Collector Crashes**: Added a task cleanup handler (`_handle_task_result`) to surface `asyncio Task exception was never retrieved` errors when background API calls fail.

## [1.0.1] - 2026-03-01
### Fixed
- Disabled `pool_pre_ping` in `asyncpg` SQLAlchemy engine configuration to completely resolve an architectural bug causing `500 Internal Server Error (MissingGreenlet)` crashes when multiple users concurrently registered vehicles and initiated background API polling.

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
