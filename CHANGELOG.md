# Changelog

## [Unreleased] - 2026-05-02
### Fixed
- ChargingEconomicsDashboard: Remove duplicate Recent Sessions Table block (copy-paste error).
- CarOverviewDashboard: Switch Promise.all to Promise.allSettled for resilience — dashboard renders partial data if individual API requests fail.
- StatisticsShell: Guard ArrowLeft/Right keyboard navigation against input/textarea elements (accessibility).
- settings/page.tsx: Fix displayVal to preserve explicit 0 values (was treating 0 as falsy).
- security-scan.yml: Scope Trivy image scan to ./backend with target:api; scope Trivy filesystem scan to ./backend (was scanning entire repo root).

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
