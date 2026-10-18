# Roadmap

Public direction for iVDrive. We ship with the community — **especially owners who share vehicle data**.

Updated: October 2026

---

## Timeline

### 2026 Q1–Q4 — Built from scratch · Škoda EV beta

**Done this year:**

- Full platform designed and built from zero (web app, API, collector, PostgreSQL, cache, Docker)
- **Škoda Connect EVs working end-to-end** (Enyaq iV, Elroq, and other Škoda Connect electric models) — trips, charging, battery, maps, live status
- Deep analytics suite (multi-method SoH, charging curves, climate/elevation penalties, cost estimates)
- Self-hosted Docker Compose stack
- Invite-only hosted **beta** at [ivdrive.eu](https://ivdrive.eu)
- Product site, documentation, community scaffolding
- **ABRP live telemetry — just shipped**

### 2027 Q1–Q2 — Volkswagen fully electric (BEV)

- First-class **Volkswagen battery-electric** support — starting with the **ID. family** (ID.3, ID.4, ID.5, ID.7, …) and other fully electric VW models where Connect APIs allow
- Same analytics depth as Škoda
- Model-specific validation with real owners
- **Not** petrol/diesel VWs — ICE is out of scope

### 2027 Q3–Q4 — SEAT fully electric (BEV)

- **SEAT / CUPRA battery-electric** vehicles (Mii Electric, Born, Tavascan, and other SEAT EVs as APIs allow)
- Not the full SEAT petrol lineup — **electric only**
- Continuous **analytics upgrades through all of 2027** (user-driven metrics)

### 2028 Q1–Q2 — Hybrids & PHEVs (fuel + electric)

- **Škoda, VW, SEAT hybrid / plug-in hybrid** capabilities
- Combined fuel + electric consumption, cost and efficiency views

### All of 2027 — always on

- Improving analytics with the community
- New metrics from user requests
- Data quality, alerts, exports

---

## We need contributors with real cars

This plan only works if owners **share vehicle data and feedback**.

Especially needed: drivers of **Volkswagen**, **SEAT / CUPRA**, and other **VW Group** EVs (and later hybrids).

- Join the beta and connect your car (or self-host)
- Tell us which metrics you want
- Validate charge curves and SoH on **your** model

**Want to unlock a brand?** Open a [Discussion](https://github.com/m7xlab/iVDrive/discussions) or [Issue](https://github.com/m7xlab/iVDrive/issues) with **model + year**, or [sponsor](https://ivdrive.eu/sponsors/) the project.

---

## Supported vehicles (today)

| Brand | Models / API | Status |
|-------|----------------|--------|
| Škoda | Enyaq iV, Elroq, other Škoda Connect EVs | **Supported (beta)** |
| VW | Fully electric VW (ID. family first, other BEVs as APIs allow) | **2027 Q1–Q2** |
| SEAT / CUPRA | Fully electric SEAT / CUPRA (Born, Mii Electric, …) | **2027 Q3–Q4** |
| Škoda / VW / SEAT | Hybrids & PHEVs (fuel + electric) | **2028 Q1–Q2** |

Exact lists grow as owners contribute data. **Don’t see your car?** Volunteer as a tester.

---

## Influence the roadmap

- Product page: [ivdrive.eu/roadmap](https://ivdrive.eu/roadmap/)
- [Discussions](https://github.com/m7xlab/iVDrive/discussions) · [Issues](https://github.com/m7xlab/iVDrive/issues)
- Contributions and sponsorships move items from “Next” to “Done”
