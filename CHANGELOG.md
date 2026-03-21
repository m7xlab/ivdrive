# Changelog

All notable changes to this project will be documented in this file.

## [v1.0.19] - 2026-03-21

### Breaking Changes 🚨
- **Analytics Overhaul**: The `v_charging_sessions_analytics` view was replaced. Charging session calculations now rely directly on the `charging_sessions` table as the authoritative source. This addresses calculation discrepancies regarding charging times.

### Added 🌟
- **Dynamic Energy Prices Integration**: Implemented automatic tracking of electricity and petrol prices across 33 European countries via `fuel-prices.eu` API. Background collector keeps prices updated weekly in a new `energy_prices` table.
- **Smart Energy Region Detection**: Integrated Nominatim reverse-geocoding. At the end of every trip, the vehicle's ISO country code is automatically retrieved from GPS coordinates and saved to the user's `user_vehicles.country_code` setting.
- **Actual Running Costs Calculation**: The dashboard now calculates running costs based on your real `actual_cost_eur` and `energy_kwh` values from completed charging sessions. Fallbacks exist to public average estimated costs when actual data is missing.
- **Savings vs Gas Metric Overhaul**: Completely refactored savings math to compare your exact real EV running cost (or country average) against a fixed 8.0L/100km ICE equivalent based on dynamic regional petrol prices.
- **Theme Preferences**: Added a new UI section under Settings -> Theme Preferences. Users can now choose "System" mode, allowing the dashboard theme to dynamically follow their desktop or mobile operating system settings, in addition to forced Light or Dark modes.

### Fixed 🛠
- Fixed an API startup crash in `vehicles.py` related to Uvicorn string loading imports (`import_from_string(self.app)`).
- Resolved missing `country_code` values persisting to `NULL` on the Settings page by ensuring it is mapped correctly in `VehicleResponse`.
- Fixed the visual math confusion in the "Savings vs Gas" UI element by clarifying labels, converting text strings, and accurately calculating exact per-100km savings differentials.
- Improved the visual text formatting for cost summaries by introducing the precise mathematical equivalent strings: "Gas: €X/100km | EV: €Y/100km".

