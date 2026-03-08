# Changelog

All notable changes to the iVDrive project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.13] - 2026-03-08
### Added
- **Umami Analytics Integration**: Added support for website analytics via Umami. The tracking script is injected server-side using Next.js `<Script strategy="afterInteractive">`. Controlled entirely via environment variables — no code changes needed to enable/disable.

### Configuration
- `SITE_ANALYTICS_URL` — Umami script URL (e.g. `https://your-umami-domain.com/script.js`)
- `SITE_ANALYTICS_KEY` — Umami Website ID from the dashboard
- Both vars must be set for the script to render. If either is missing, analytics are silently skipped.

## [1.0.12] - 2026-03-07
### Added
- **All-Time Time Budget**: New `/analytics/time-budget` backend endpoint aggregates `vehicle_states` and `charging_states` entirely in the database. Returns lifetime totals (Parked, Driving, Charging, Ignition, Offline) without requiring a date range — frontend fetches once on mount.
- **Charging Session Reconstruction**: `charging_states` rows are point-in-time snapshots; sessions are now reconstructed using gap detection (>30 min gap = new session) with a +5 min buffer per session for the final snapshot interval.
- **Movement Stats Endpoint**: `/analytics/movement-stats` for period-scoped data (Top Places, Activity Timeline), with proper `first_date`/`last_date` clamping to the query window.
- **`SkodaCommandClient`**: New backend client using the `myskoda` library for vehicle commands (climate, charging, lock/unlock, honk/flash, wake). Separate from `SkodaAPIClient` (httpx) used for telemetry.
- **Vehicle Commands UI**: Apple-style compact tiles on the Commands subpage — icon top-left, label bottom-left. Climate card (start + temperature), Unlock card (SPIN input), plus tiles for Charging, Lock, Honk/Flash, Wake.
- **"Vehicle Commands (Beta)" Settings Toggle**: Preferences section in Settings stores `ivdrive_show_commands` in `localStorage` (default `false`). Commands tab is hidden until the user explicitly enables it.
- **Map Theme Awareness**: Movement map now switches between CartoDB Dark / Light tiles based on the active app theme, observed via `MutationObserver`.

### Fixed
- **Manual Refresh Blocked by Smart Polling**: `DataCollector.collect_vehicle()` now accepts `force: bool` — bypasses the parked-vehicle early-return when triggered by a `vehicle_refresh` event.
- **`formatDuration` Duplicate Definition**: Three copies of `formatDuration` in `MovementDashboard.tsx` caused a fatal Turbopack build error (`the name formatDuration is defined multiple times`). Reduced to a single definition; stray closing braces also removed.
- **Time Budget "0m Total"**: Previous implementation attempted to sum `first_date == last_date` snapshot rows — now correctly skips zero-duration rows and uses session reconstruction for charging.

## [1.0.11] - 2026-03-05
### Added
- **PWA (Progressive Web App) Support**: Implemented a web manifest (`manifest.json`) and mobile metadata to allow "Add to Home Screen" installation on iOS and Android.
- **Standalone Display Mode**: Configured the UI to hide browser chrome when launched from the home screen, providing a native app-like experience.

### Fixed
- **Favicon Alignment**: Standardized the site favicon to use the official iVDrive logo across all platforms.
- **Mobile UI Meta**: Added specialized Apple web-app status bar configurations for improved translucent styling on iPhones.

## [1.0.10] - 2026-03-05
### Fixed
- **Dynamic Cost Logic**: Replaced hardcoded €0.25/kWh estimate with a real-time weighted average derived from actual charging session costs.
- **API Data Flow**: Patched `telemetry.py` schema to include `actual_cost_eur`, fixing a bug where cost data was being stripped from API responses.
- **Analytics Precision**: Increased decimal precision for "Total Energy Added" and updated "Full Charge" reference to 77kWh (accurate for Enyaq iV 80).
- **Dynamic Savings Calculation**: "Savings vs Gas" now dynamically compares real EV charging costs per 100km against the diesel baseline, instead of using a static estimate.

### Added
- **Analytics Debug Logs**: Integrated a browser-side debug suite for verifying telemetry calculations in real-time via Developer Tools.
- **Session Metrics**: Added "Average Energy per Session" to the Total Energy dashboard block.

## [1.0.9] - 2026-03-05
### Added
- **Analyst-Grade Statistics View (12-Block View)**: A major overhaul of the vehicle detail page, introducing 12 specialized data blocks for deep telemetry analysis.
- **Efficiency Pulse**: Real-time kWh/100km tracking with dynamic trend arrows comparing current performance against the last 30 days.
- **Charging Mix Dashboard**: New donut chart visualizing the ratio of AC vs. DC charging sessions.
- **Running Cost Analysis**: Automated estimation of monthly operating costs and a breakdown of €/100km.
- **Cold Weather Impact**: Dedicated "Winter Penalty" metric showing the percentage increase in consumption due to low temperatures.
- **Trip Type Categorization**: Automatic breakdown of driving habits into Short, Commute, and Long Haul categories.
- **Phantom Drain Tracker**: Estimated battery percentage and kWh loss while the vehicle is parked.
- **Total Energy Throughput**: Lifetime and period-based kWh consumption tracking.
- **Diesel Savings Tracker**: Real-time calculation of savings compared to an equivalent diesel vehicle (7L/100km benchmark).

## [1.0.8] - 2026-03-03
### Added
- **Mobile-First Adaptive UI (v1.0.8)**: Complete refactor of the dashboard shell and statistics views for phone screens.
- **Bottom Navigation Bar**: Replaced the fixed sidebar with a native-feel bottom navigation bar for mobile users (Tesla/App style).
- **Responsive Statistics Dashboards**: Refactored horizontal data tables (Trips, Charging Stats, Car Overview) into adaptive vertical cards for small screens.
- **Hero Section Optimization**: Re-engineered the Map-Car overlay with smart vertical/horizontal gradients that adapt based on device orientation.

### Fixed
- **Smart Polling v2.3.2 (The Infinite Stabilization Loop)**: Fixed a critical logic flaw where the stabilization counter (intended for post-drive capture) was incorrectly resetting to 0 for parked vehicles. This fix resolves the issue where cars would poll every 5 minutes for "ghost activity" before skipping 10 minutes.
- **Interval Synchronization**: Optimized the `_sync_vehicles_from_db` daemon to prevent it from resetting "Active" polling jobs back to "Parked" during the 90-second background sync.
- **Charging Stats Layout**: Fixed "squeezed" metrics in the Charging Power & Rate dashboard by implementing a responsive dual-view `StatTable`.
- **Hero UI Clarity**: Removed "foggy" backdrop blurs from the map transition and boosted z-index for Leaflet controls, ensuring a sharp, high-definition look on all devices.

## [1.0.7] - 2026-03-03
### Fixed
- **Smart Polling v2.3.1 (Ghost Polling)**: Refined the `car_active` logic to correctly handle the "Online but Idle" state. Stabilization cycles no longer force active polling for stationary vehicles that happen to be reachable via the Skoda API.
- **Collector Stabilization**: Added explicit logging to confirm when the stabilization period completes and the collector returns to the parked interval.

## [1.0.6] - 2026-03-03
### Added
- **Data Sovereignty (Extract My Data)**: Users can now export 1 year of historical telemetry (drives, charging, etc.) as a ZIP-compressed JSON (v1.0) for migration to self-hosted instances.
- **Announcement System**: Implemented a platform-wide notification engine for administrators to broadcast features and updates to users.
- **Notification Persistence**: New Alembic migrations and models to store user-specific notification states (read/unread/dismissed).

### Fixed
- **Alembic Versioning**: Resolved "Multiple head revisions" migration conflict, linearizing the database schema history.
- **Export Engine**: Fixed 500 errors caused by VIN decryption logic and SQL type mismatches between telemetry tables.
- **CORS Headers**: Explicitly exposed `Content-Disposition` in middleware to enable browser-initiated file downloads from the API.
- **Smart Polling v2.3**: Optimized the collector by caching connection states, significantly reducing redundant DB I/O during vehicle polling.

## [1.0.5] - 2026-03-02
### Added
- **Manual WLTP Override**: New input field in "Add Vehicle" and "Vehicle Settings" to manually set WLTP Range (km), bypassing Skoda API omissions.
- **Efficiency Priority Data Logic**: Refactored the engine to prioritize user-set WLTP values over model-based fallbacks or drive data.
- **Enhanced Data Capture**: Removed artificial filtering from Efficiency and Range charts. The system now records and displays data from the very first second of a state change (Motion, Charging, or AC), ensuring the most comprehensive telemetry possible.
- **Smart Polling v2.1 (Collector Stabilization)**: Added a "post-activity" buffer in `collector.py`. The system now forces 3 extra high-frequency polls after the car stops moving/charging to ensure final odometer readings and GPS coordinates are captured.
- **Stability Patches**: Resolved a potential memory leak in the `DataCollector` and improved background task tracking for manual refreshes.
- **GDPR Compliance**: Implemented "Delete My Account" with `ON DELETE CASCADE` for total data erasure across all telemetry tables.

### Changed
- **Workspace Cleanup**: Moved 15+ legacy test and update scripts into `_deprecated_scripts/` to clean the backend root.

### Fixed
- **Efficiency Engine**: Resolved "empty chart" issues for vehicles where the Skoda API failed to provide WLTP data by implementing a robust multi-source fallback system.
- **Metadata Fetching**: Optimized the `DataCollector` to perform synchronous metadata refreshes upon vehicle registration or manual refresh requests.

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
