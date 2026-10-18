---
sidebar_position: 2
title: FAQ
---

# FAQ

## General

### Is iVDrive free?

The project is open source (Elastic License 2.0). The hosted service is in **invite-only beta**. Self-hosting is free to run yourself.

### Which cars are supported?

Škoda Connect electric / PHEV vehicles first (e.g. Enyaq iV). Other VW Group brands where Connect APIs allow are on the [roadmap](../community/roadmap.md).

### Do I need a dongle?

No. iVDrive is software-only and uses official Connect APIs.

## Data

### What data do you store?

Telemetry needed for analytics: SoC, range, charging, trips, position, odometer and related states. See [Add a vehicle](../getting-started/add-vehicle.md).

### Where is my data?

Hosted beta: on the ivdrive.eu infrastructure. Self-hosted: on **your** infrastructure.

### Can I export my data?

Yes, where offered in Settings (format varies by version).

## Account

### How do I join the hosted beta?

[Request an invite](https://ivdrive.eu/register).

### How do I enable 2FA?

[Create an account](../getting-started/create-account.md#two-factor-authentication-2fa).

## Self-hosting

### Minimum hardware?

A small VPS or NAS with Docker is enough for personal use.

### Can I disable AI features?

Yes — omit AI API keys / disable workers in configuration.

## Still stuck?

- [Troubleshooting](./troubleshooting.md)
- [GitHub Discussions](https://github.com/m7xlab/iVDrive/discussions)
- [Issues](https://github.com/m7xlab/iVDrive/issues)
