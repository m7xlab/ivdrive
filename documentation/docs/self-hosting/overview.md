---
sidebar_position: 1
title: Overview
---

# Self-hosting overview

Run iVDrive on your own hardware for full control.

## What you get

The same product as the hosted beta:

- Web UI (Next.js)
- REST API (FastAPI)
- Collector (polls Škoda Connect)
- PostgreSQL
- Valkey (Redis-compatible cache)

## When to self-host

- You want vehicle data on **your** server / NAS
- You’re comfortable with Docker
- You want to customise or extend the stack

If you prefer zero setup, use [ivdrive.eu](https://ivdrive.eu).

## Prerequisites

- Docker Engine + Docker Compose
- ~2 GB RAM free (plus database growth)
- Outbound HTTPS to Škoda Connect APIs
- A place for secrets (`.env`)

## High-level steps

1. Clone the repository
2. Configure `.env`
3. `docker compose up -d`
4. Initialise the database
5. Register + promote an admin
6. Add your vehicle

Detailed guides:

- [Docker Compose](./docker-compose.md)
- [Configuration](./configuration.md)
- [Landing proxy](./landing-proxy.md) *(optional for production)*
- [Upgrades](./upgrades.md)

## License note

iVDrive is under **Elastic License 2.0 (ELv2)**. Self-hosting is welcome; offering it as a managed third-party service is not permitted. See the repository `LICENSE`.
