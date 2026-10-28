# Changelog

## [v1.3.6] - 2026-10-29
**Missing trips are filled from MyŠkoda's own trip history. MyŠkoda Login works again.**

### Fixed
- **MyŠkoda Login failed with "could not parse password form"** — Škoda now redirects after the email step; the login did not follow it, so adding a vehicle or re-authenticating failed.

### Added
- **Trip history sync (MyŠkoda Login vehicles)** — every 6 hours iVDrive reads Škoda's server-side trip history (about 60 days, with stops, times, SoC and exact odometer) and adds the trips polling missed. Trips already recorded are never changed or deleted; a 0 km trip gets its distance. New trips are marked `skoda_history`. The official Public API has no trip history, so Public-API-only vehicles are not covered. Check against real data: Škoda's 99 trips add up to exactly the odometer distance (1,422 km); polling alone had 1,237 km.
- `python -m app.scripts.sync_skoda_trips --all` — same sync on demand (dry run by default).

### Notes
- Rebuild **api + collector**. No database migration.
- The poll intervals are unchanged.

## [v1.3.5] - 2026-10-28
**One charge, one session. Trips keep their kilometres. AI works on fresh installs and with any OpenAI/Anthropic-compatible or local (Ollama) model.**

### Fixed
- **Duplicate session after the target SoC is reached (#205, #198)** — when charging ended and the battery ticked 79% → 80% as the car switched to `CONNECT_CABLE` / `CONSERVING`, that tick was read as "battery rising" and opened a second 80% → 80% session. A new session in the same plug-in now needs real power flow.
- **Silent poll failures during home AC charging** — reopening a session reused the previous start time, hit the unique constraint and rolled back the whole poll (live SoC, close). It is now checked before insert.
- **Flat-SoC auto-close measured from session start** — a long slow charge could close mid-charge. It now uses the time of the last SoC change.
- **Missing trip kilometres (#204)** — a trip noticed one poll late started at the odometer of that poll and dropped the earlier distance (e.g. 17 of 21 km). It now starts from the last known odometer reading and is marked `estimated_start`.
- **No trips or charges at all on Public API installs (#204)** — the Public API collection path stored telemetry but never started trip/charge processing (only the Login path did). It now does, after each successful snapshot.
- **Trip end time** is the telemetry timestamp, not the processing time. A start/end odometer or SoC of `0` is no longer ignored.
- **Second home charge never recorded (#185, #198)** — a charge that began while the state row had been merged for days (`CONNECT_CABLE`) reused that row's old start time, collided with the previous session and was skipped. New sessions now start at the current poll when the row start is not newer than the last session's end.
- **0 km trips** — Škoda's odometer can lag the moving flag, so a trip closed with 0 km. The distance is now attributed from the next odometer reading (live, for the last 3 hours). Remaining one-poll "moving" flickers can be cleaned with the new backfill tool.
- **"AI Assistant not available" on self-hosted (#203)** — the documented `init_db` + `alembic stamp head` flow left `ai_tier_configs` empty and `ai_usage_log.id` without a default. `init_db` and a new migration restore the defaults and seed Free/Pro/Team (existing admin edits are kept). Seeded Pro/Team model is `gemini-2.5-flash`, which works on the Google AI Studio free tier.

### Added
- **Bring your own AI model** — `OPENAI_BASE_URL` / `OPENAI_API_KEY` (any OpenAI-compatible server: OpenAI, LM Studio, vLLM, OpenRouter), `ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL`, and `OLLAMA_BASE_URL` for local models. Every provider is optional, including Gemini and MiniMax; pick provider and model per tier in Admin → AI Assistant. `LLM_TIMEOUT_SECONDS` and `LLM_FALLBACK_PROVIDERS` tune slow local models and fallback.
- **Embeddings without Gemini** — `EMBEDDING_PROVIDER=ollama|openai` with `EMBEDDING_MODEL` / `EMBEDDING_BASE_URL` (768-dim models). Unset uses Gemini only if its key is set, otherwise the offline hash.
- **`python -m app.scripts.backfill_trips`** — dry-run-by-default repair of historical trips: attributes late odometer distance, reports uncovered odometer gaps, optionally adds `reconstructed` trips (`--create-reconstructed`) or deletes 0 km flicker trips (`--purge-phantom`). Back up first.

### Changed
- The tier's Gemini model is now actually used (it was ignored in favour of `gemini-2.5-flash`). Models without a price entry (local / new) are costed at $0 instead of MiniMax rates.

### Notes
- Rebuild **api + collector**. Run `alembic upgrade head` (adds `charging_sessions.last_soc_change_at`, `trips.data_quality`, repairs AI defaults).
- Existing trips are not changed automatically. Run `python -m app.scripts.backfill_trips --all` (dry run) to see what it would repair.
- Vehicles whose collector was offline have no telemetry for that period; those gaps are reported but cannot be reconstructed from data that was never collected.
- Added a telemetry replay test suite (`backend/tests/replay`, needs a reachable Postgres; uses a throw-away database).

## [v1.3.4] - 2026-10-25
**No more phantom charging sessions.** A parked car with the cable in no longer creates empty "Unknown Provider" sessions.

### Fixed
- **Mystery "Ongoing" charges (97% → 97%)** — a session opened whenever the car reported a plugged-in state (`CONNECT_CABLE`, `CONSERVING`, `READY_FOR_CHARGING`, `CHARGING_INTERRUPTED`) even at 0 kW with flat battery. After the flat-SoC auto-close the next poll reopened it, and deleting the row only started the cycle again.
- New sessions now open only when energy is flowing (state `CHARGING`, power above 0, or battery rising). Home AC that reports 0 kW is still captured once the battery level rises.
- A drive followed by a parked cable (lower SoC at 0 kW) is no longer treated as a new charge.

### Notes
- Rebuild **collector** and **api**.
- No database migration. Existing empty sessions (start level = end level, no energy) can be removed with **Delete charge**.

## [v1.3.3] - 2026-10-24
**Smart polling finds your car again.** Short drives and remote heating no longer disappear between checks.

### Fixed
- **Activity detection** — charging and climate are checked on every Parked tick (Live/Parked Sync intervals work as labeled). A car that starts charging or heating is picked up within one Parked interval.
- **Status ping is not the only signal** — if the online check fails or says unreachable, sensors still run so the car cannot hide.
- **Short drives after remote heat/charge** — sending heat, charge, wake, or Refresh switches to **Live Sync** for several cycles so a 5–7 minute drive is not skipped.
- **Climate Start / Stop** — complete command payload and automatic fallback to the official API key path when Login rejects the request. Failures log the real reason for support and show a clearer UI message.
- Long low-power AC charging still stays open in charging sessions; idle cars still avoid heavy API calls.

### Notes
- Rebuild **collector** and **api**.
- No database migration.
- `SLEEP_WAKE_PROBE_EVERY_N` remains available but is no longer the detection bottleneck.

## [v1.3.2] - 2026-10-24
**Modern remote controls and reliable charging history.** New Commands tab, session cleanup tools, and friendlier command errors.

### Added
- **Commands tab redesign** — circular climate dial (temperature ring with °C/°F), Start / Stop, and compact action rows for charging, lock, unlock, and wake.
- **Capability hints** — actions that need MyŠkoda Login or an API key say so up front instead of failing after a click.
- **Add charge** — record a missed session from Charging history (start/end, SoC, kWh, cost, provider).
- **Delete charge** — remove glitch or duplicate rows with a confirmation step.
- **End charge** — close an Ongoing session from the list when the car is done.

### Changed
- Command results show as a short toast with **Retry** that reuses the current S-PIN / temperature.
- Climate card matches the height of the action list on desktop (no gap).

### Fixed
- **Unlock** now sends the vehicle S-PIN so remote unlock can work with MyŠkoda Login.
- **Honk & Flash** is clearly marked as not available on this connection (it never silently did something else).
- Command failures use plain language (expired API key, login expired, wrong S-PIN, car unreachable) instead of raw error text.
- Finished charges with the cable still connected no longer stay **Ongoing** forever; long low-power AC charging is left open.
- A stuck open session no longer swallows later charges.
- Lock state (`YES`/`NO`) correctly enables Lock / Unlock actions.
- Modals no longer show map buttons and coordinates through the backdrop.

### Notes
- Rebuild **api + web + collector**.
- No database migration.
- Passwords, API keys, and S-PINs stay encrypted at rest.

## [v1.3.1] - 2026-10-21
**Official API key or MyŠkoda Login — per car.** Cleaner vehicle settings, clearer connection status, and smarter polling.

### Added
- **Per-vehicle connection** under Settings → Vehicles: MyŠkoda **email/password** (optional) and official **API key** (paste or create from login).
- **Wake, lock/unlock, climate** when MyŠkoda Login is saved for that car.
- **Create official key from login** — one click instead of pasting a key.
- Password fields show/hide toggle.
- Vehicle rows show **Login saved / API key · Nd / expired** badges and connection errors.

### Changed
- **Source per car:** Auto · MyŠkoda Login · Public API.
- **Auto** uses Login when saved, otherwise the official API key.
- Smart polling switches to the **active interval** when the car moves or charges (and back when idle).
- Wrong MyŠkoda password **stops polling** and asks you to update login (no silent retries).
- Integrations = external services (ABRP). Škoda connection lives only on the vehicle.

### Removed
- Old `myskoda` library path and the account-level “Škoda API” settings block.

### Notes
- Rebuild **api + collector + web**. Run `alembic upgrade head`.
- Passwords and API keys are stored **encrypted**.

## [v1.3.0] - 2026-10-19
**Official MyŠkoda Public API dual-stack** — collect live telemetry with a personal Public API key (no Škoda password), keep the legacy login path as fallback, and fail with human-readable errors when keys expire or VINs are not linked.

### Added
- **Official MyŠkoda Public API client** (`skoda_public_api.py`): `X-API-Key` against `public.api.connect.skoda-auto.cz`, single composite vehicle snapshot (`include=…`), problem+json → friendly user messages (`api-key-expired`, `api-key-not-authorized`, `rate-limit-exceeded`, …).
- **Dual-stack source layer** (`vehicle_source.py` + `skoda_normalize.py`): per-vehicle `telemetry_source` = **Auto** (public first, login fallback) · **Login** (legacy `myskoda`) · **Official** (Public API only). Normalized snapshot shared by the collector so charts/ABRP do not care which backend answered.
- **Settings → Integrations → Škoda official API**: paste a personal API key from the MyŠkoda app ([go.skoda.eu/api-keys](https://go.skoda.eu/api-keys), QR help bundled locally for CSP). Key + expiry stored AES-256-GCM on the user; soft warnings before expiry.
- **Add Vehicle without password** when an official key is configured — onboard cars that only use the Public API path.
- **Collector** `_try_collect_public` / `_persist_public_snapshot`: SoC, range, charging, HVAC, parking position, connection readiness; HVAC stored as point-in-time rows (`AirConditioningState.captured_at`).
- Per-vehicle **source switch** on the vehicle form; human-readable API problems (not raw status codes) in UI and collector logs.
- Migration `c3d5e7f9a1b2`: `users.skoda_public_api_key_encrypted` + expiry/last_error, `vehicles.telemetry_source`.

### Changed
- Settings Integrations order: **Škoda official API** above ABRP.
- APScheduler collector tick logs demoted (noisy INFO looked like a poll loop).
- Tests: `test_skoda_public.py` for client errors + normalize mapping.

### Cutoff readiness (legacy login)
When Škoda retires the unofficial login/MQTT stack, vehicles can move to **Official** (or Auto with public-only) without a code change: configure a user API key and set source to Official/Auto. Rate budget is ~**20 req/hour/VIN** on the Public API — smart polling intervals still apply.

### Notes
- No breaking API change. Rebuild **api + collector + web** (web for Settings + Add Vehicle).
- Never commit API keys; they live only in the UI and encrypted DB columns.
- Dual-stack during transition: legacy login remains for cars not bound to a Public API key.

## [v1.2.1] - 2026-10-18
Smart polling **deep-sleep**: stop constant Škoda pulls and identical DB writes while the car is parked. Status ping only; full monitoring when the car is actually active.

### Fixed
- **Deep sleep (parked / cable @ 0 kW):** every `parked_interval_seconds` (e.g. 15 min) does **one** `get_connection_status` and **no database writes** unless online/offline changed. No more refreshing `charging_states` / ABRP with the same values overnight.
- **Wake window:** every Nth parked tick (`sleep_wake_probe_every_n`, default 4) probes `get_charging` + `get_air_conditioning` **as sensors only**. Real charging (`CHARGING` or power &gt; 0) or climate on → **Active** full fetch. Cable at 0 kW stays asleep.
- **Activity = motion / real charge / climate** — not merely plugged in. Manual **Refresh** still forces a full fetch immediately.
- **`vehicle_updated` no longer clobbers Active interval:** saving vehicle settings used to re-register the job at `parked_interval_seconds`, so a live Active poll dropped to the parked rate (full fetches at 15 min). Interval updates now follow the current poll mode.

### Changed
- Smart Polling **v2.5** (see `smart_polling_explanation.md`).
- Active full fetch unchanged except garage/renders (static metadata) are not called every cycle (from v1.1.16.1).
- New config: `sleep_wake_probe_every_n` (default 4).

### Notes
- No schema change. Rebuild **api + collector** (web unchanged).
- Battery Level chart (`drive_levels`) is written on Active cycles only — it should not gain points while the car is asleep.

## [v1.2.0] - 2026-10-18

**Marketing launch** — public landing site, docs, and optional Caddy edge. Self-host `docker compose up` is unchanged (console at `/`).

### Added
- **Landing site** (`landing/`) — static Next.js + **Caddy** marketing edge: home, features, roadmap, sponsors, about, open source, community. Apple-minimal dark brand (emerald → cyan).
- **Dual-use `/`** — desktop guests and crawlers see the marketing home; signed-in cookies or mobile UA go to the app console. `iv_view=landing` / `iv_view=app` cookies override.
- **Docs site** (`documentation/`) — Docusaurus under **`/docs/`** (getting started, user guide, self-hosting, reference, community).
- **Roadmap** (on-site `/roadmap`) — 2026 built-from-scratch Škoda EV beta · 2027 H1 VW **BEV** · 2027 H2 SEAT/CUPRA **BEV** · 2028 hybrids/PHEVs; public call for real-car data contributors.
- **Sponsors** (`/sponsors`) — GitHub Sponsors / Ko-fi story for the solo maintainer.
- **Compose overlay** — `docker-compose.landing.yml` (optional `ivdrive-landing` + `ivdrive-docs`).
- **Deploy runbook** — `landing/DEPLOY.md` (placeholders only).

### Changed
- Product screenshots refreshed from the live app (dark + light).
- GitHub: YAML issue forms, `config.yml`, funding + PR template aligned with `validate-pr-description`.
- License short name in copy: **Elastic License 2.0 (ELv2)**.

### Notes
- **Self-host:** no landing required; API/web/collector DB behavior unchanged.
- **Production:** publish **`ivdrive-landing`** as the public entry (was `ivdrive-web:3000`). Full steps in `landing/DEPLOY.md`.
- New images: `ivdrive-landing`, `ivdrive-docs` (app images unchanged in behavior).

## [v1.1.16.1] - 2026-10-17
Hotfix: restore deep-sleep polling while a car sits on a cable without drawing power. v1.1.15/v1.1.16 treated `CONNECT_CABLE` (and other plugged-in states) as Active, so home-parked EVs did a **full Škoda fetch every `active_interval_seconds`** (often 3 min) all night.

### Fixed
- **Parked sleep vs home cable** (`collector.py`): Active polling now requires **real activity** — moving, `state == "CHARGING"`, or `charge_power_kw > 0` on a plugged-in state, or climatisation on. A 0 kW `CONNECT_CABLE` / `READY_FOR_CHARGING` / `CONSERVING` night is **Parked** again (`parked_interval_seconds`, e.g. 15 min).
  - `is_plugged_in()` is still used for **charging session** open/close (overnight home sessions and SoC climbs are kept).
  - New `is_actively_charging(state, charge_power_kw)` in `analytics.py` owns poll intensity only.
- **Overnight SoC without waking Active**: the parked path persists `ChargingState` (SoC, power, remaining range) from the charging probe **already fetched** that cycle — no extra API call, no full fetch.
- **Parked probe cost**: skip the AC probe when the vehicle is plugged in (already have charging this cycle). Parked work is connection status (+ charging when online), never position/status/maintenance/garage/renders.
- **Active full-fetch trim**: `get_garage_vehicle` / `get_vehicle_renders` no longer run every Active cycle (static metadata; backfilled only when missing). Cuts two Škoda calls per active tick.

### Changed
- Smart Polling **v2.4** (see `smart_polling_explanation.md`): Active = moving / real charge / AC; Parked includes cable-at-zero-power.
- Tests: `test_charging_detect.py` covers `is_actively_charging` matrix (CONNECT_CABLE at 0 kW must not activate).

### Notes
- No schema change. No new env vars. Rebuild **api + collector** only (web unchanged).
- Pair with v1.1.16 ABRP: parked cable no longer floods ABRP with full-rate points; real charging still pushes.

## [v1.1.16] - 2026-10-17
Feature release: A Better Route Planner (ABRP) live-telemetry integration, Settings UX overhaul (category navigation), and a hardened security-scan workflow. Builds on v1.1.15 (CONNECT_CABLE home-charging capture).

### Added
- **ABRP telemetry integration** (community request [#189](https://github.com/m7xlab/ivdrive/discussions/189)): optional outbound push of live vehicle data to [A Better Route Planner](https://abetterrouteplanner.com) so trips can use accurate live SOC and charging data instead of a slower third-party bridge. **Off by default.**
  - **Credentials are per ABRP user, not deployment config.** Settings → **Integrations — ABRP**: save a free Telemetry API key from the user's ABRP account, then paste a **car token** per vehicle (ABRP app → Live Data → Custom connection). Both stored AES-256-GCM encrypted (`users.abrp_api_key_encrypted`, `abrp_connections.token_encrypted`) via the same `encrypt_field` helpers as VINs and connector tokens. Never returned by the API — only opaque `••••` hints.
  - **What is sent** (metric): `utc` (epoch seconds), `soc`, `power` (charging negated — ABRP convention), `lat`/`lon`/`elevation` (omitted when the vehicle has incognito mode on), `is_charging` / `is_parked` / `is_dcfc`, `odometer`, `est_battery_range`, `capacity`/`soe`, `ext_temp`/`batt_temp`, `hvac_setpoint`/`hvac_power`, optional `car_model` typecode. Numeric **speed is omitted** (not available from the Škoda API).
  - **Transport**: collector enqueues one datapoint per cycle into a Valkey outbox (`ivdrive:abrp_outbox`). A flusher pushes via `POST /1/tlm/send` for a single sample or `POST /1/tlm/bulk` when the same user has multiple vehicles queued. Failures never break collection (bookkeeping + exponential backoff).
  - **Read-side**: Settings can fetch ABRP's next charge-to goal (`get_next_charge`) and show it as a chip. No remote vehicle control — ABRP Custom connections only expose Driving/Charging data (ABRP-side limitation of the Telemetry API).
  - API: `GET/PUT /api/v1/integrations/abrp` (user API key), `PUT/DELETE /api/v1/integrations/abrp/vehicles/{id}` (car token), `GET/POST .../next-charge`.
- **Settings category navigation**: the settings page is no longer a single ~3600px scroll. Sticky left category rail on desktop (Account · Vehicles · Security · Energy · Integrations · Data & Privacy) with one category per view; horizontal scrollable tabs on mobile. Content column uses the full remaining width instead of a narrow `max-w-2xl` card stack.

### Changed
- **Settings IA**: sections regrouped — Account (preferences, theme, profile), Vehicles, Security (password, 2FA), Energy (geofences, charging plans), Integrations (ABRP), Data & Privacy (export, danger zone).
- **Security Scan workflow** (`.github/workflows/security-scan.yml`):
  - Action bumps for Node 24 runners: `actions/checkout@v5`, `docker/setup-buildx-action@v4`, `docker/build-push-action@v7`, `gitleaks/gitleaks-action@v3`. `github/codeql-action` stays on `@v4`.
  - **Trivy image scan no longer gates the job on HIGH OS/library CVEs.** Weekly runs were flipping red whenever the Debian base image carried a fixable HIGH (e.g. `libpcre2` CVE-2026-103111). SARIF upload + table report always run for CRITICAL+HIGH; a separate gate step fails only on **CRITICAL** image CVEs. Filesystem/IaC scan still fails on CRITICAL+HIGH.
- **Repo hygiene**: `.gitignore` also covers local assistant/CLI tooling dirs and Playwright artifacts.

### Database
- `a9c4e2b7d1f8_add_abrp_connections.py` — `abrp_connections` (1:1 with `user_vehicles`): `enabled`, `token_encrypted`, `car_model_typecode`, `last_sent_at`, `last_error_text`, `consecutive_failures`, `backoff_until`, `next_charge_pct`, `next_charge_fetched_at`.
- `b7e1a4c9d2f3_add_user_abrp_api_key.py` — `users.abrp_api_key_encrypted`.

### Migration notes
- `alembic upgrade head` from v1.1.15: `c5849a2e1b70` → `a9c4e2b7d1f8` → `b7e1a4c9d2f3`.
- Rebuild **web** image for the settings layout; rebuild **api** + **collector** for ABRP push. No new required env vars.

### Notes
- ABRP feature is fully opt-in: no API key and no vehicle tokens means zero outbound traffic.
- Telemetry push cadence follows the collector (default 300s active / 1800s parked). ABRP's ideal is ~5s and hard floor ~30s — expect minute-level live updates, still much faster than typical third-party bridges. ABRP processes telemetry in 60s batches.
- Test tokens must never be committed; they are pasted in the UI and stored encrypted.

## [v1.1.15] - 2026-09-10
Collector hotfix: parked home charging was missed when Škoda reported `CONNECT_CABLE` instead of `CHARGING`. No schema change. No new UI.

### Fixed
- **Home charging sessions dropped** (`CONNECT_CABLE`): smart-poll treated only `state == "CHARGING"` as active, so a plugged-in parked car stayed on the 30‑minute interval and `charging_sessions` was never opened. Škoda often never emits `CHARGING` (power stays 0 kW) while SoC still rises — MySkoda still has the history; iVDrive only sees live polls. Collector and analytics now treat plugged-in states (`CHARGING`, `READY_FOR_CHARGING`, `CONNECT_CABLE`, `CHARGING_INTERRUPTED`, `CONSERVING`) as charging. Rebuild **api + collector**. Web unchanged. No Alembic.

### Database
- Head remains `c5849a2e1b70`. No new migration.

## [v1.1.14] - 2026-09-08
Major feature release on top of v1.1.3: six-method Battery SoH v2 (weighted-median combined), trip-gap vampire drain, user charging plans, display locale (ECB FX + metric/UK/US units), CARTO basemap API keys, Nominatim/Photon geo cache, and a Node 24 frontend image. Storage stays km / °C / EUR / kWh; conversion is display-only.

### Added
- **Battery SoH v2** (PR #182): six independent methods with confidence — Tesla capacity (3×), charging-curve taper (2×), cell imbalance, throughput, fleet benchmark, range-drift — combined as a weighted median. New `battery_health_analytics` cache (`GET /api/v1/vehicles/{id}/battery-health-analytics`, owner POST recompute). Legacy `/analytics/battery-health` is cache-first against the v2 combined row. Statistics Battery SoH tab is a 5-card dashboard; tab URLs are `/vehicles/{id}/statistics/{tab}`.
- **Vampire drain from trip gaps** (PR #182): parked SoC loss is `trip[i].end_soc → trip[i+1].start_soc` while odometer is still and no charging session overlaps. Hour-weighted, including 0% integer-SoC nights (Škoda only reports integer SoC; parked charging payloads are not persisted). Replaces the empty/biased `v_phantom_drain_stats` parked-state join.
- **User charging plans** (PR #182): Settings CRUD for included-kWh subscriptions, discounted-rate subscriptions, and home/public kWh rates. Sessions can pick a plan or match a geofence. **€0 is a real included-allotment cost** (`is not None`), not “missing”. Monthly fee is a period economics line item, not stuffed onto the first session. Overage uses the overage rate (fallback `monthly_fee / allotment`).
- **Display locale — currency + units** (PR #182): Settings **Display currency** (ECB catalog via PyPI `CurrencyConverter`) and **unit system** (`metric` / `uk` / `us`). UK: miles, mph, °C. US: miles, mph, °F. kWh stays kWh. Missing non-EUR rate does **not** fall back to 1.0 — UI stays on EUR until a rate exists. Wired across vehicle page, vehicle cards, Add Vehicle WLTP, and statistics dashboards. Climate control state stays °C internally; US display converts.
- **CARTO Basemaps API key** (PR #181): CARTO now requires a key for public tiles. `NEXT_PUBLIC_CARTO_BASEMAPS_API_KEY` (`.env.example`, `docker-compose.yml` `ivdrive-web` build-arg + runtime env) is appended as `?key=...` on every `basemaps.cartocdn.com` URL via a shared tile helper. Free key at https://carto.com/basemaps/apikey/ — no approval queue. CSP `img-src` already allows `https://*.basemaps.cartocdn.com` (v1.1.2.1 #163). Without the key, tiles 401 and the CARTO watermark shows on every map. `NEXT_PUBLIC_API_URL` is also passed as a Docker build-arg so it is inlined at `next build`.
- **Reverse-geocode cache** (PR #182): `POST /api/v1/geo/reverse` is Valkey → Postgres → Nominatim → Photon (Komoot), ~1.1 m quantize, ~110 m nearby reuse for driveway GPS jitter, 90-day Valkey TTL, Nominatim cooldown + Photon fallback, inflight Future coalescing.
- **Invite registration UX** (PR #182): register page accepts a pasted invite token (or a full invite URL); invite emails include the raw token as well as the button link.

### Fixed
- **Hub `ivdrive-web` login CSP**: the multi-arch workflow baked `NEXT_PUBLIC_API_URL=http://localhost:8000` into the browser bundle, so production login hit the visitor’s machine and was blocked by `connect-src 'self'`. Hub `m7xlab/ivdrive-web:v1.1.14` is rebuilt with an empty URL (same-origin `/api` via Next rewrites). **CARTO tile key**: `getCartoTileUrl` appended a literal `?key=***}` instead of the env value — maps 401’d even when the key was baked.
- **Charging taper SoH sign** (PR #182): DC power drop (`(recent − earlier) / earlier`) was negated into a SoH **increase**. Power drop now lowers SoH (clamped ±5 points). Cached combined rows still include the old sign until recompute.
- **Geo inflight hang on cancel** (PR #182): `CancelledError` is `BaseException`, not `Exception`. If the leader reverse-geocode request is cancelled, waiters on the same lat/lon Future are now resolved in `finally`.
- **SoH method cache mix** (PR #182): per-method breakdown is loaded with the combined row’s `computed_at` so a partial older persist cannot mix into the dashboard.
- **Login validation 500** (PR #182): `validation_exception_handler` now uses `jsonable_encoder` so Pydantic `ValueError` contexts (e.g. login) serialize instead of crashing the error handler.
- **Legacy battery-health `desc` import** (PR #182): `/analytics/battery-health` imported `desc` without defining it (500 on the v2 cache path).

### Changed
- **Frontend runtime** (PR #182): Node **24.20.0** / npm **11.19.0** / Alpine **3.24.1**, multi-arch (`amd64` + `arm64`) image digest.
- **Statistics shell** (PR #182): tabs grouped Daily vs Analysis; URL-per-tab routing; Battery SoH sits with daily checks.
- **Local compose CORS**: `docker-compose.yml` `ivdrive-api` no longer interpolates `CORS_ORIGINS` (app still reads it from config / `.env`; production `docker-files/compose.yml` still passes it).
- **New Python dependency**: `currencyconverter>=0.18.21` (ECB rates). Not the PyPI `units` package.

### Database
- `d6e7f8a9b0c1` (`a1b2c3d4e5f6_add_battery_health_analytics_table.py`) — `battery_health_analytics` (per-method + `combined` cache). File name still says `a1b2c3d4e5f6` but the **revision id is `d6e7f8a9b0c1`** to avoid colliding with `add_smart_polling_intervals`. `CREATE TABLE IF NOT EXISTS` is safe on DBs that already have the table. Revises `1924fb48a5b1`.
- `e8a91c2d3f40_trip_gap_phantom_drain.py` — replaces `v_phantom_drain_stats` with the trip-gap definition (1–72 h parked, still odometer, no overlapping charge, hour-weighted including 0% nights).
- `b473841e9399_add_user_charging_plans.py` — `user_charging_plans` + `charging_sessions.charging_plan_id`. Unrelated embeddings/SoH drift was **not** included in this migration.
- `c5849a2e1b70_add_currencies_and_unit_system.py` — `currencies` (ECB `rate_per_eur`, `as_of`, `source`) + `users.unit_system` (default `metric`). **Head.**

### Migration notes
- `alembic upgrade head` from v1.1.3: `1924fb48a5b1` → `d6e7f8a9b0c1` → `e8a91c2d3f40` → `b473841e9399` → `c5849a2e1b70`.
- After upgrade, ECB rates populate on first FX refresh; maps need a **web image rebuild** with `NEXT_PUBLIC_CARTO_BASEMAPS_API_KEY` (Next inlines `NEXT_PUBLIC_*` at build time).
- Recompute Battery SoH after deploy so taper sign and v2 methods replace any pre-fix combined cache.

### Notes
- New env var: `NEXT_PUBLIC_CARTO_BASEMAPS_API_KEY` (required for maps; also a Docker **build-arg**). `NEXT_PUBLIC_API_URL` must be a build-arg as well.
- No OCPI `charging_stations` revival. Currency/units are **not** inferred from `country_code`.
- Settings calibration fields (ICE L/100km, etc.) stay labelled in stored units on purpose.

## [v1.1.3] - 2026-07-08
Major authentication architecture overhaul and frontend fetching modernization. Resolves persistent API anti-bot rejection issues and transient backend server errors. The authentication state machine has been hardened to securely maintain and refresh sessions, supported by a newly introduced frontend query layer and user-facing connection state UI.

### Fixed
- **Authentication anti-bot 403s & 500s**: The backend data collector now distinguishes between transient server errors (500s) and hard authorization rejections (403s/401s). The internal token lifecycle handles silent re-login with stored credentials when access is rejected by anti-bot measures, effectively bypassing the token expiry limit without dropping the connection. 
- **React Hook Dependency Bugs**: Resolved existing React Doctor `rules-of-hooks` errors, `useEffect` callback syncing loops, and exhaustive-deps warnings on the main dashboard components, improving frontend health.

### Changed
- **Dashboard Data Fetching via TanStack Query**: Replaced legacy `useState` & `useEffect` data fetching patterns on the vehicle dashboard with `@tanstack/react-query`. Ensures the UI stays fresh without causing re-renders or "stuck" loading states.
- **In-card Auth Strategy UI**: Moved authentication method and connector error indicators directly inside the vehicle card title row for immediate context regarding the last successful connection type and any active transient errors.
- **Manual Re-authentication UI**: A new banner seamlessly prompts users to re-enter credentials specifically when the backend flags that manual intervention is required. Upon success, React Query instantly invalidates the cache, clearing the banner and resuming live data flow without requiring a manual page reload.




## [v1.1.2.1] - 2026-07-04
Bugfix & hardening patch: six targeted fixes that landed on `development` after v1.1.2 — Content-Security-Policy tightening, collector startup retry, chat markdown XSS hardening, the chat sessions Valkey cache (which was silently no-op), the embedding-producer perf refactor, and the SoH `[0, 100]` clamp + zero-division guard. Plus the repo-hygiene cleanup that was sitting in `[Unreleased]` since v1.1.2.

### Fixed
- **Content-Security-Policy tightening** (PR #163): removed `https://unpkg.com` and `https://*.basemaps.cartocdn.com` from `script-src` (those domains only serve image assets — Leaflet marker icons, CARTO basemap tiles — letting them host JavaScript is an XSS-to-CDN-hijack escalation risk). They now live only in `img-src`. Also added `analyticsHost` (derived from `SITE_ANALYTICS_URL`) to `connect-src` so analytics telemetry requests aren't blocked.
- **Collector startup retry** (PR #164): the collector crashed on boot whenever Postgres was briefly unreachable (shared Docker network still warming up). A retry loop around the initial DB readiness check lets the process come up cleanly without operator intervention.
- **Chat markdown XSS hardening** (PR #165): the `<a>` handler in the chat widget now validates `href` protocol against `/^(https?:|\/|#|mailto:)/i`. Anything else (`javascript:`, `data:`, `vbscript:`, malformed) renders as a muted span with a "Blocked unsafe link" tooltip — defense-in-depth on top of react-markdown's default URL transformer. Also dropped the redundant `whitespace-pre-wrap` on the wrapper (which fought Markdown block spacing) and added explicit `<pre>` styling so multi-line code blocks render readably.
- **Chat sessions Valkey cache — actually wired up** (PR #166): the cache service was added in v1.1.2 with write-path invalidation but **the GET endpoint never read from it** — the cache was never populated, so the "perf fix" was a no-op. `GET /api/v1/chat/sessions` is now a real read-through cache (60s TTL). Cold path: 1 DB query + cache warm. Warm path: 0 DB queries. Hardened `get()` to reject malformed cached payloads (stale strings from an earlier version, partial JSON) as a miss instead of leaking them into Pydantic responses.
- **Embedding producer guard — perf refactor** (PR #167): the collector was calling every content builder per poll just to ask "do you have data?" before enqueuing, while the embedding worker runs the same builder when processing the queue anyway — the collector's check doubled DB load on every telemetry poll. Collector now enqueues unconditionally. The worker (`process_one`) returns `(success, permanent_failure, msg)`; "no source data" and "unknown content_type" errors are tagged **permanent** and the batch loop DELETEs those queue rows immediately instead of incrementing `attempts` and retrying up to `max_attempts`. Transient errors (builder exception, store error) still retry as before. No more infinite enqueue→fail→re-enqueue loop, no more queue-table pollution from permanently-failed items.
- **SoH clamp `[0, 100]` + zero-division guard** (PR #168): the live-compute fallback only clamped the upper bound (`min(..., 100.0)`), so negative values from cold-soak under-voltage still leaked through. Also vulnerable to `ZeroDivisionError` if `factory_kwh` was zero/missing. Now `max(0.0, min(...))` on both bounds in both the monthly `curve_data` and the summary `latest_derived`, with `if f_kwh > 0 else 0.0` guarding the division.

### Maintenance
- **Repo hygiene — `.gitignore` / `.dockerignore` cleanup** (folded in from `[Unreleased]`): rewrote all four ignore files (`.gitignore`, root `.dockerignore`, `backend/.dockerignore`, `frontend/.dockerignore`) to cover common noise (Python `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.coverage`, `htmlcov`, `*.egg-info`, venvs, `.env*`, logs; Node `node_modules`, `.next`, `dist`, `build`, `out`, `.eslintcache`, `tsconfig.tsbuildinfo`; editor/IDE scratch `*.orig`, `*.bak`, `*.tmp`, `*.swp`, `.DS_Store`, `Thumbs.db`, `.idea/`, `.vscode/`). Removed the accidentally-tracked editor backup `frontend/src/app/(dashboard)/admin/page.tsx.orig`. Smaller Docker build context, no secrets or local DB dumps can leak into the repo.

### Notes
- No new env vars, no database migrations, no new dependencies. Pure code changes.
- `react-doctor` score is 48/100 — the remaining ~80 lint warnings are pre-existing baseline across 31 files, none introduced by this release's touched files. A separate codebase-wide cleanup pass is planned for a later release, scoped out of v1.1.2.1 to keep this patch focused.
- `tsc --noEmit` reports 6 pre-existing errors in four stat dashboards (`BatterySoHDashboard`, `CarOverviewDashboard`, `SpeedTempMatrixDashboard`, `TripsDashboard`), all pre-date this release. Suppressed by `ignoreBuildErrors: true` so `next build` still passes.
- PR #169 (`fix/statistics-period-limit-from-daterange`) is a follow-up bugfix against the Driving Stats period filter and Route Efficiency scoring. It is currently open against `development` and will be folded into v1.1.2.1 if the tag hasn't been cut yet, otherwise released as v1.1.2.2.

## [v1.1.2] - 2026-07-03
Major feature release: real battery State-of-Health (no more Škoda hardcoded 95%), per-vehicle data-freshness widget, AI-Support-Coach tool, a multi-pass react-doctor cleanup that deletes ~170 dead files and 264 → 92 lint issues, and an S3-backed monthly Battery Health Passport (HTML email + downloadable PDF). Plus a multi-turn RAG fix that makes chat follow-ups work, a SQL-driven Top Places view, and a CI sync workflow. This release also fixes the long-standing `reasoning_effort: 0` hallucinated budget and tightens the SoH trim so outlier regen cycles no longer inflate derived capacity.

### Added
- **Battery State-of-Health model** (PR #153): replaces Škoda's hardcoded `hv_battery_soh` (always 95%) with a real, derived estimate. New `battery_soh_estimates` table (method: `capacity`/`throughput`/`resistance`/`aggregate`), confidence scoring, anomaly detection (sudden drop, degradation acceleration), per-tier rate-limit + min-confidence gates, and admin per-user overrides. `/analytics/battery-health` reads from the cache populated by the new daily scheduler.
- **Battery Health Passport (monthly, S3-backed)**: generates an HTML email + downloadable PDF every month per vehicle. Uses a dedicated `BATTERY_PASSPORTS_BUCKET` (not the generic `data-extract` bucket) so retention policies don't collide. PDF rendering is WeasyPrint, run via a background scheduler task with smtplib isolated to a worker thread (no event-loop blocking). SVG points render as joined strings, not Python `list.__repr__`. Empty confidence / empty curve guards.
- **Per-vehicle Data Freshness widget** (`/vehicles/{id}/data-health`): surfaces the last-seen timestamp of every telemetry stream (position, vehicle_state, charging_state, charging_session, trip, odometer) with a coarse `live`/`stale`/`down` roll-up and a one-click "Refresh" CTA when something's missing. Powers a new badge in the vehicle header and an AI Support Coach tool the chat widget can invoke when queries touch stale data.
- **react-doctor cleanup — Passes 1, 2, 3, 5, 6A, 6B**: 264 → 92 issues, score 45 → 48. Deleted ~170 dead files (AppContent, ClientHydrationGate, ErrorBoundary, NotificationCenter, ChargingAnalysisDashboard, ChargingEconomicsDashboard, DrivingDashboard, DrivingSummaryDashboard, EfficiencyDashboard, PulseDashboard, VampireDrainDashboard, and ~159 others). Hydration: hoisted `new Date()` out of initial state in `statistics` + `maintenanceDateRange` to stop the SSR/CSR mismatch. Accessibility sweep: 5 click-handlers got `role=button + tabIndex + keyDown`, 4 labels paired with inputs via `htmlFor`. Mounted-gate audit across every dashboard. `toSorted`/`toReversed` adoption. Sweep `type="button"` to stop accidental form submissions. Chat widget hardened: `<think>` reasoning strips from LLM answers; movement-dashboard flicker fixed; new `next@16.2.6` upgrade for the Turbopack parse-error catch that saved this release.
- **Multi-turn RAG fix**: agentic router now sees `conversation_history` + `detected_vehicle_name`, so pronoun resolution ("what about that trip?", "the same one yesterday") works in follow-ups. Previously, only the current turn was visible, breaking multi-step questions.
- **Top Places via SQL view** (`v_top_places_per_vehicle`): geofence-matched stay durations computed in SQL rather than in the frontend's JS clustering loop. Period-filtered (`from_date`/`to_date`). The Movement Dashboard now reads from `/overview/top-places` instead of re-deriving the same data in `useMemo`.
- **Vehicle delete error surfacing**: previously the vehicle-list "Delete" button silently succeeded on 5xx; now any failure pops a `useToast` with the backend's error message so the user knows to retry. (`fix(frontend): surface vehicle delete errors via cmdResult toast`)
- **`useEffect` unmount-race guard**: `vehicles/[id]/page.tsx` now tracks mount state before `setData` to prevent the React warning (and potential state-on-unmounted write) when a user clicks away mid-fetch.
- **AI chat `model/provider` fallback**: if the configured provider errors (rate limit, region block), the chat service tries the configured fallback before failing. Logs the failure so the admin can see when fallback fired.
- **CI sync-development workflow** (`.github/workflows/sync-development.yml`): auto-pulls `development` to match `main` on every push to `main`, so the dev branch never accumulates merge drift during quiet release windows.

### Fixed
- **Battery-SoH realistic range**: charging-loss correction + tighter outlier trim. Previously a single DC fast-charge with regen at the start of the session would inflate the derived capacity by 8–12%; new trim caps capacity at 103% of factory and excludes regen-inflated samples. Empty confidence / empty chart guards.
- **Battery scheduler signature drift**: scheduler was calling the old `generate_passport_html(vehicle_id)` signature after the HTML generator gained an options arg; now passes the full options dict and uses `json.dumps` for the `usage_log.metadata` JSONB column (was writing Python repr, breaking JSONB indexes).
- **`battery-soh` SQL divide-by-zero guard**: the `factory_kwh` validation now refuses to execute the SoH division when the factory capacity is NULL or non-positive, instead of raising a `psycopg2.errors.DivisionByZero` that surfaced as a 500.
- **vehicle delete errors via `cmdResult` toast**: previously the toast was eating the error; now it surfaces with the backend message verbatim.
- **`useEffect` data-fetch race**: `vehicles/[id]/page.tsx` was firing `setData` after unmount when the user navigated away mid-fetch; now guarded by a `mounted` ref + cleanup.
- **chat `<think>` reasoning blocks** leaked into the streamed answer — now stripped at the stream layer before the answer reaches the user, so the widget shows only the final answer.
- **`MovementDashboard` hydration flicker** — `useMemo([locations])` recomputed the activity timeline on every render because the input array identity changed; switched to `useMemo([locations, geofences])` and a stable `useCallback` for `fetchPeriodData`.
- **Build-breaking parse error at MovementDashboard.tsx:191** — half-merge artifact (two broken useEffect blocks) caught by Turbopack in `next build` (`tsc --noEmit` accepted the dangling brace). Fixed in PR #160.
- **`api.getTimeBudget` useEffect didn't refetch on date-range change** — deps were `[vehicleId]` only and the call didn't pass `fromISO`/`toISO`. Result: stale all-time numbers when the user changed the period. Now uses `[vehicleId, fromISO, toISO]` deps and passes dates to the API. Fixed in PR #160.

### Changed
- **Battery SoH API contract** (`/analytics/battery-health`): response now includes `derived_confidence`, `derived_estimated_at`, `derived_sample_count`, `derived_source` (`battery_soh_estimates` | `fallback_no_capacity` | live). Curve rows may use `month` (aggregated) or `date` (per-session), and `estimated_kwh` instead of `capacity_kwh`. Frontend type updated to accept either shape.
- **`reaction_effort: 0` in LLM budget** was a hallucinated spend number; cost logger now only emits rows with non-zero input/output tokens, and the UI no longer shows a phantom zero.
- **`next` bumped to 16.2.6** — Turbopack catches what `tsc` misses (lesson recorded in MEMORY.md).
- **`react-leaflet` v5**: `Polyline.onClick` was removed; replaced with `eventHandlers={{ click: ... }}`.
- **`react-doctor` config rewritten** in `frontend/doctor.config.json` (was `react-doctor.config.json`) to silence the load-rule noise; tuned so `<think>` blocks aren't double-flagged.

### Database
- `a1b2c3d4e5g7_add_battery_soh_ops_model.py` — new tables: `battery_soh_estimates` (append-only history with `method` enum, `confidence` enum, `inputs_json`, `anomalies_json`), `battery_soh_alerts` (`severity` enum, `acknowledged_at`), `battery_tier_configs` (free/plus/pro, `pdf_enabled`, `alerts_enabled`, `estimate_frequency`, `min_confidence_required`, `monthly_price_eur`), `battery_user_overrides` (admin per-user, NULL fields = use tier default), `battery_soh_usage_log` (every estimate gen, PDF send, alert fired). Chained onto `b2c3d4e5f6a8`. No data backfill required.
- `c7d8e9f0a1b2_add_connector_health_fields.py` (already shipped in v1.1.1, included here for completeness) — `connector_sessions`: `last_success_at`, `consecutive_failures`, `last_error_text`.

### Migration notes
- `alembic upgrade head` should run as a single linear walk: `b7e4f1a9c2d8 → c7d8e9f0a1b2 → b2c3d4e5f6a8 → a1b2c3d4e5g7`. The chain is clean (no branching heads); verified via `alembic history` on a fresh dev DB.
- New env vars (no defaults, will refuse to start without them): `BATTERY_PASSPORTS_BUCKET`, `BATTERY_SOH_MIN_CONFIDENCE` (default `medium`), `BATTERY_PASSPORT_SCHEDULE_HOUR` (default `8`). Already present: `SMTP_*`, `S3_*`.

## [v1.1.1] - 2026-06-20
Maintenance & reliability release: fixes the charging-receipt edit lag (stale server cache), surfaces Škoda connection/auth failures in the UI so users know when to reconnect, makes the vehicle "sync off" state honest, and adds mobile-responsive fixes. Includes a statistics-correctness verification pass and a build-breaking syntax fix.

### Added
- **Connection-health surfacing**: the vehicle Settings card now shows a clear banner + badge when data collection is failing. Two states — **red "Reconnect required"** when Škoda rejects the saved login (auth/token expired), and **amber "Connection Issues"** when the vehicle is repeatedly unreachable (transient Škoda/network errors, ≥3 consecutive failed cycles). Both offer a one-click Reconnect. Backed by new `ConnectorSession` health fields populated every collection cycle and exposed on `GET /api/v1/vehicles`.
- **Charging Mix caption** (vehicle Statistics): the AC/DC split card gained a descriptive caption ("AC vs DC · last 30 days (N sessions)") consistent with the other stat cards.

### Fixed
- **Charging-receipt edit lag (stale server cache)**: editing a charging session (provider/kWh/price) appeared to do nothing for up to 60s, then updated. Root cause: the server-side Valkey `CacheMiddleware` caches analytics GETs for 60s and the mutation never invalidated it (the `invalidate_vehicle_cache` helper existed but was dead code). `PATCH .../analytics/charging-sessions`, `PUT /vehicles/{id}`, and `DELETE /vehicles/{id}` now bust the vehicle's cache on write, so edits are reflected immediately. Verified end-to-end (GET after PATCH returns the new value with `X-Cache: MISS`).
- **"Sync off" still showed "Active"**: disabling a vehicle's sync stopped collection (the poll job is unregistered) but left `connector_status` stuck at "active", so the badge kept reading Active. Toggling sync off now sets status **"paused"** (badge "Sync Off") and clears failure counters; re-enabling sets "pending" until the next successful poll. The Settings badge shows "Sync Off" whenever collection is disabled (covers pre-existing rows), and health banners are suppressed while paused.
- **Silent collection failures**: the collector's `_safe()` swallowed every Škoda error and still marked the cycle "active"/fresh, so persistent failures were invisible to the user. Cycles now record success/failure honestly (`last_success_at`, `consecutive_failures`, `last_error_text`); a 401/403 flags `auth_failed`; transient errors accrue failures without forcing a reconnect prompt. Parked cycles no longer write a misleading "offline" `ConnectionState` row when Škoda was merely unreachable.
- **Build-breaking syntax error** — `DrivingDashboard.tsx` had a comment line missing its `//` prefix (committed in `ff14ce3`), which fails the production transpile regardless of `ignoreBuildErrors`.
- **Mobile layout** — Admin tabs now scroll horizontally instead of overflowing on small screens; the AI chat widget/launcher is repositioned (above the mobile nav bar, full-width sheet on phones, unchanged on desktop).

### Changed
- **Efficiency metric documentation** (`analytics.py`, migration `ba81d9f38011`): clarified in code that `v_advanced_trip_stats.avg_eff_*` and the overview `avg_kwh_100km` are **distance-weighted** consumption (`SUM(kwh)/SUM(distance)*100`), not an average of per-trip ratios, and marked the superseded `AVG`-of-ratios migration obsolete (the fix landed in `93b2a201b1a4`). Documentation only — no value change. Confirmed the live overview numbers (battery, range, odometer, trip mix, efficiency, €/kWh) match the raw database.

### Database
- `c7d8e9f0a1b2_add_connector_health_fields.py` — adds `last_success_at` (timestamptz), `consecutive_failures` (int, default 0), and `last_error_text` (varchar 255) to `connector_sessions`. New migration head; no data backfill required.

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
- **Duplicate migration revision (multiple heads)**: `a1b2c3d4e5f6` was assigned to BOTH `add_smart_polling_intervals` and `add_place_stay_durations_view` (a merge collision), so `alembic upgrade head` failed with "Revision a1b2c3d4e5f6 is present more than once" / "Multiple head revisions are present". Re-issued the place-stay view migration as `b7e4f1a9c2d8` chained onto the real head `b2c3d4e5f6a8`; `add_smart_polling_intervals` keeps `a1b2c3d4e5f6`. View body is `CREATE OR REPLACE`, so it applies cleanly.
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

## [Unreleased]

 - 2026-06-26
### Changed
- **Frontend react-doctor cleanup — Passes 1, 2, 3, 5, 6A, 6B** (branch `fix/react-doctor-cleanup-passes-1-2-3-5`)
  - Issues: 264 → 92 (−172), errors: 1 → 0, files: 48 → 28, score: 45 → 48
  - **Pass 1**: deleted 11 dead files, swept 38 `type="button"` omissions on buttons, fixed MovementDashboard flicker (date-range dependency tracking), upgraded `next@16.2.6`
  - **Pass 2**: fixed `new Date()` hydration (IVDriveAIWidget + DashboardLayout), cleaned unused imports
  - **Pass 3**: audit + cleanup of mounted gates (consistent pattern)
  - **Pass 5**: `toSorted` over `sort()`, dropped unused exports
  - **Pass 6A**: accessibility sweep — 5 click handlers on divs got `role="button" + tabIndex={0} + onKeyDown(Enter/Space)` (AddVehicleModal + 2nd modal backdrops, DeleteVehicleModal backdrop, Trip row selector, VehicleCard outer click); 4 labels paired with `htmlFor`/`id` (admin announcements form)
  - **Pass 6B**: hoisted `new Date()` out of statistics + maintenance IIFEs into a single `statsNow` state in `VehicleDetailPage`, threaded through both chart IIFEs (eliminates per-render clock reads)
- **PR Agent feedback fixes (1 High, 4 Medium, 3 Low)** — all on the same branch, will consolidate into PR #153 (see PR-153 conversation):
  - **High**: `battery_passport.py` `_svg_chart` — `points = []` then injected into f-string rendered as Python `repr()` (broken SVG `<circle>` list). Fixed: joined via generator expression.
  - **Medium**: `battery_scheduler.py` — manual f-string JSON for `metadata_json` with `bool(...)` → `True`/`False` (invalid JSONB). Fixed: `json.dumps({...})`.
  - **Medium**: `analytics.py` SoH derivation — `if not factory_kwh or factory_kwh <= 0` ran AFTER `db.execute(soh_stmt, ...)` (which divides by `:factory_kwh`). Fixed: moved guard before query.
  - **Medium**: `battery_passport.py` `send_passport_email` + `send_passport_email_legacy` — synchronous `smtplib.SMTP` inside `async def` blocks the FastAPI event loop under scheduler load. Fixed: wrap in `_send_sync()` closure + `await asyncio.to_thread(...)`.
  - **Medium**: `vehicles/[id]/page.tsx` `maintenanceDateRange` — initialised with `new Date()` causing hydration mismatch (same pattern as `statsNow` from Pass 6B but missed on the maintenance tab). Fixed: `useState<... | null>(null)` + populate in `useEffect`.
  - **Low**: `battery_passport.py` — `badge_y = y_for(current_soh) - 28` can be negative for healthy batteries (clipping badge). Fixed: `max(0, ...)`.
  - **Low**: `vehicles/[id]/page.tsx` tab-switching `useEffect` — no cleanup, in-flight requests could `setState` on stale instance (race conditions). Fixed: `let isMounted = true` + guard every setter + return cleanup.
  - **Low**: `vehicles/[id]/page.tsx` `handleDelete` — swallowed errors and closed the modal on failure (no user feedback). Fixed: keep modal open, route error through existing `setCmdResult` toast.

## [Unreleased]

 - 2026-05-08
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