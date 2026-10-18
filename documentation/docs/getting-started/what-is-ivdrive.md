---
sidebar_position: 1
title: What is iVDrive?
---

# What is iVDrive?

iVDrive is a **premium EV data monitoring** application built for Volkswagen Group electric vehicles — starting with Škoda Connect APIs.

Instead of a thin factory app, you get:

- A **single dashboard** for vehicles, trips, charging and statistics
- **Deep analytics** (battery health methods, charging curves, climate and elevation penalties)
- **Optional integrations** (ABRP live telemetry)
- A **self-hostable** open-source stack

## The problem

Modern EVs generate rich telemetry — battery state, charge power, location, HVAC load — but OEM apps usually show only a snapshot. Drivers who care about efficiency, degradation and cost cannot answer basic questions:

- How much did this trip really consume?
- Is my battery still healthy after 3 years?
- Which public charger is actually fast?
- How much did home charging cost last month?

## The solution

iVDrive collects telemetry via the official Škoda Connect API (through a background **collector**), stores history in PostgreSQL, and visualises it in a modern web UI.

You can:

1. **Use the hosted service** at [ivdrive.eu](https://ivdrive.eu) (invite-only beta), or
2. **Self-host** the identical stack with Docker Compose

## Core ideas

| Idea | Meaning |
|------|---------|
| **Ownership** | Self-hosting is first-class; your vehicle credentials stay on your infrastructure |
| **Depth** | Curves, distributions and long-term trends — not vanity metrics |
| **Community** | Built in the open under Elastic License 2.0 |
| **VW Group first** | Škoda today; other Connect-compatible brands where feasible |

## Name

**iV** — Volkswagen Group’s electric vehicle family suffix (Enyaq iV, …)  
**Drive** — the driver’s view of their data

Next: [Quick start →](./quick-start.md)
