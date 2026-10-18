---
sidebar_position: 4
title: Battery health
---

# Battery health (SoH)

State of Health tells you how your pack ages — not just today’s percentage.

## Multi-method SoH

iVDrive estimates SoH using several methods and combines them (weighted median) with a **confidence** score:

1. **Capacity-based** estimates (usable energy vs original)
2. **Charging-curve taper** behaviour
3. **Cell imbalance** signals
4. **Throughput / cycle** accounting
5. **Fleet benchmark** (community range, where enabled)
6. **Range drift** over time

## What you see

Open **Statistics → Battery SoH**:

- Combined SoH percentage
- Confidence
- Degradation trend
- Method breakdown
- Alerts if something looks wrong

## Battery Health Passport

Where enabled, iVDrive can generate a periodic **health passport** (email / PDF) summarising pack status — useful for resale or service visits.

## Good to know

- SoH improves as more charging sessions are collected
- Occasional deep AC charges help estimators (within manufacturer guidance)
- Cold weather can temporarily hide capacity — look at trends, not single points

Related: [Charging](./charging.md), [Settings](./settings.md)
