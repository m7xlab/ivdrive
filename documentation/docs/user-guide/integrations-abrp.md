---
sidebar_position: 7
title: ABRP integration
---

# ABRP integration

Push live data to [A Better Route Planner](https://abetterrouteplanner.com) so routes reflect your actual battery.

## What is sent

- State of charge (SoC)
- Charging status
- Position

Enabled **only** if you turn it on. Credentials are stored encrypted.

## Enable

1. Go to **Settings → Integrations**
2. Connect your ABRP account / token
3. Toggle live telemetry
4. Verify in ABRP that the vehicle appears

## Disable

Turn the toggle off (or clear the token) to stop sharing.

## Limitations

| Supported | Not supported |
|-----------|----------------|
| Live SoC | Remote climate / lock |
| Charging power / status | Vehicle commands from ABRP |
| Position for routing | Full OEM feature parity |

These limits are on the ABRP side for Custom connections.

## Privacy

- Opt-in only
- Encrypted at rest
- Self-hosters: ABRP tokens stay in your deployment
