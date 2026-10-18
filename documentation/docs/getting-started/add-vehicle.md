---
sidebar_position: 4
title: Add a vehicle
---

# Add a vehicle

iVDrive connects to your car through **Škoda Connect**. You will need:

- A Škoda Connect account (same as the MyŠkoda / Connect app)
- An electric or PHEV vehicle supported by the Connect API (e.g. Enyaq iV)

## Steps

1. Open **Add vehicle** on the dashboard
2. Enter your **Škoda Connect** email and password
3. Submit — the collector starts pulling telemetry
4. Wait for the first sync (minutes, sometimes longer on first run)

Your vehicle appears as a card with:

- Model and nickname
- Battery percentage and range
- Odometer / distance
- Link to the full vehicle page

## Multiple vehicles

Add as many Connect accounts / vehicles as you need. Use the **carousel / vehicle list** to switch between them.

## What data is collected?

Typical telemetry includes:

- Battery state of charge (SoC), range, charging state and power
- Odometer and trip distance
- Position and travelled routes
- HVAC / cabin-related state (where exposed by the API)
- Timestamps for freshness

Exact fields depend on the vehicle and Connect API version.

## Credentials & security

:::warning
iVDrive stores Connect credentials **encrypted** to poll your vehicle. Prefer a dedicated Connect password if that matches your threat model.
:::

- Hosted beta: credentials live in the service’s secure storage
- Self-hosted: credentials stay in **your** database and secrets config

## Troubleshooting

| Symptom | What to try |
|---------|-------------|
| Login to Connect fails | Verify MyŠkoda app works; check for lockouts / CAPTCHA |
| Vehicle missing after add | Wait for sync; check collector logs (self-host) |
| Data stale | Ensure the car has connectivity; see [Troubleshooting](../reference/troubleshooting.md) |

More help: [FAQ](../reference/faq.md)
