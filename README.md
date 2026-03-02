# iVDrive

<p align="center">
  <a href="https://ivdrive.eu">
    <img src="assets/ivdrive_logo_v1_original.png" alt="iVDrive Logo" width="200">
  </a>
</p>

<p align="center">
  <strong>Premium Electric Vehicle Data Monitoring for Volkswagen Group EVs</strong>
</p>

<p align="center">
  Use iVDrive online at <a href="https://ivdrive.eu">ivdrive.eu</a> — request an invite, get approved, and view your EV data. Self-hosting is available for those who prefer to run the stack themselves.
</p>

<div align="center">

  **Beta** — **iVDrive is in active development.** We're currently in an invite-only beta to ensure stability as we scale. 

  **Request an invite at [ivdrive.eu/register](https://ivdrive.eu/register)** to join the waitlist!

  **We welcome contributors, feedback, and new users!**

</div>

<p align="center">
  <a href="https://ivdrive.eu"><strong>Try iVDrive (Beta)</strong></a> •
  <a href="#-getting-started"><strong>Getting Started</strong></a> •
  <a href="docs/README.md"><strong>Documentation</strong></a> •
  <a href="#-community--contributing"><strong>Community</strong></a> •
  <a href="FUNDING.md"><strong>Support</strong></a>
</p>

---

## 🚀 What is iVDrive?

iVDrive is a premium EV data monitoring app for Volkswagen Group vehicles (starting with Škoda). Use it **online at [ivdrive.eu](https://ivdrive.eu)** — request an invite, join the beta, and get a single dashboard for trips, charging, efficiency, and statistics. If you prefer to run the stack yourself, you can self-host with Docker.

### Why iVDrive?

- **Beta Access** — Use online at [ivdrive.eu](https://ivdrive.eu). Request an invite, get approved, and start viewing your data.
- **VW Group EV focus** — Built for Škoda Connect first; designed to extend to other Volkswagen Group EVs.
- **Single dashboard** — Trips, charging, efficiency, locations, and driving statistics in one place.
- **Self-host optional** — For advanced users: run the full stack yourself with Docker (see [Getting Started](#-getting-started)).

## 🏗️ Architecture

iVDrive runs as a multi-container Docker environment:

| Component     | Technology | Purpose                                      |
| ------------- | ---------- | -------------------------------------------- |
| **Frontend**  | Next.js (React, App Router), Tailwind, Recharts, React-Leaflet | Web UI and charts |
| **Backend API** | FastAPI, SQLAlchemy (async), Pydantic | REST API, auth, vehicle commands |
| **Collector** | Python worker | Polls Škoda API, stores telemetry in the database |
| **Database** | PostgreSQL | Users, vehicles, telemetry history |
| **Cache**    | Valkey (Redis-compatible) | State, cache, pub/sub |

The frontend proxies `/api/*` to the backend so you can serve everything from one origin (e.g. `https://ivdrive.eu`).

## 🎯 Who is iVDrive for?

- **EV owners** with Škoda (and compatible VW Group) vehicles — use [ivdrive.eu](https://ivdrive.eu) to see your driving and charging data in one place.
- **Self-hosters** (optional) — if you have the know-how, you can run the stack on your own server or NAS.
- **Developers** — build on the REST API or extend the collector; see [CONTRIBUTING.md](CONTRIBUTING.md).

## 📸 See it in action

Screenshots from the live app at [ivdrive.eu](https://ivdrive.eu). Light and dark theme available — see [assets/screenshots/](assets/screenshots/).

| Login | Add vehicle | Vehicle overview |
|-------|-------------|------------------|
| [![Login](assets/screenshots/login_light_theme.png)](assets/screenshots/login_light_theme.png) | [![Add vehicle](assets/screenshots/add_vehicle_light_theme.png)](assets/screenshots/add_vehicle_light_theme.png) | [![Overview](assets/screenshots/overview_light_theme.png)](assets/screenshots/overview_light_theme.png) |

| Homepage | Settings |
|----------|----------|
| [![Homepage](assets/screenshots/homepage_light_theme.png)](assets/screenshots/homepage_light_theme.png) | [![Settings](assets/screenshots/settings_light_theme.png)](assets/screenshots/settings_light_theme.png) |

## 🚀 Getting Started

### Use iVDrive online (no setup)

1. Go to **[https://ivdrive.eu](https://ivdrive.eu)**.
2. Open the **Register** page and fill in the form.
3. Wait for the email with your invite to be sent.
4. Click the link in the email to verify your email.
5. Register a new account with your email and password.
6. **Add your vehicle** with requested credentials.
7. Your data will sync and appear in the dashboard — trips, charging, statistics, and more.

### Self-host (optional, for advanced users)

If you prefer to run the stack yourself (e.g. on your NAS):

1. **Clone the repository**
   ```bash
   git clone https://github.com/m7xlab/iVDrive.git
   cd iVDrive
   ```

2. **Configure environment** — Copy [.env.example](.env.example) to `.env` and set `POSTGRES_PASSWORD`, `VALKEY_PASSWORD`, `JWT_SECRET_KEY`, `ENCRYPTION_KEY` (see `.env.example` for notes).

3. **Run with Docker Compose**
   ```bash
   docker compose up -d
   ```
   - Web UI: http://localhost:3035 (or your host/port).
   - API: http://localhost:8000.

4. **Initialize Database** (Required for Self-Hosters)
   Ensure the database and tables are created correctly:
   ```bash
   docker compose exec ivdrive-api env PYTHONPATH=/app python -m app.scripts.init_db
   docker compose exec ivdrive-api env PYTHONPATH=/app alembic stamp head
   ```

5. **Promote Admin User** (Required for Self-Hosters)
   After registering your first user via the UI, promote them to superuser to access the admin panel:
   ```bash
   docker compose exec ivdrive-api env PYTHONPATH=/app python -m app.scripts.promote_user --email your@email.com
   ```

6. **Add your vehicle** in the UI with your Škoda Connect credentials.

For more detail, see [Project overview](docs/project_overview.md) and the [docs](docs/README.md).

## 📚 Documentation

- [Documentation index](docs/README.md) — Using iVDrive, self-hosting, and project overview.
- [Self-hosting guide](docs/self-hosting.md) — Run the stack with Docker on your own server or NAS.
- [Changelog](CHANGELOG.md) — Release history and notable changes.
- [Roadmap](ROADMAP.md) — Current focus and planned directions.

## 🤝 Community & Contributing

We welcome contributions: bug reports, feature ideas, and pull requests.

- [Contributing guide](CONTRIBUTING.md) — How to set up your environment and submit changes.
- [Code of conduct](CODE_OF_CONDUCT.md) — Community standards.
- [Security policy](SECURITY.md) — How to report vulnerabilities (please do not use public issues for security).

See our [Contributing Guide](CONTRIBUTING.md) for details.

## 📄 License

iVDrive is available under the [Elastic License 2.0](LICENSE) (ELv2). You may use, modify, and distribute the software subject to the terms in the license. The license does **not** allow offering the software to third parties as a hosted or managed service. See [LICENSE](LICENSE) for the full text.

## 🌟 Star History

[![Star History Chart](https://api.star-history.com/svg?repos=m7xlab/iVDrive&type=Date)](https://star-history.com/#m7xlab/iVDrive&Date)

---

<p align="center">
  <strong>Ready to monitor your EV data?</strong><br>
  <a href="https://ivdrive.eu">Try iVDrive</a>
</p>

<p align="center">
  <a href="https://github.com/m7xlab"><img src="assets/m7xlab-high-resolution-logo-transparent.png" alt="m7xlab" width="120" /></a><br>
  <strong>m7xlab</strong> (m7xlabaroty) · <a href="https://ivdrive.eu">iVDrive</a> · <a href="THANK-YOU.md">Thank you</a>
</p>

<p align="center">
  <a href="https://github.com/m7xlab/iVDrive/graphs/contributors">
    <img src="https://contrib.rocks/image?repo=m7xlab/iVDrive" alt="Contributors"/>
  </a>
</p>
