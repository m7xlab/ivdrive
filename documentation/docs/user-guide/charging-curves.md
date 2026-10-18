---
sidebar_position: 2
title: Charging curves
---

# Charging curves

See **how your car actually charges** — not just “it took 40 minutes”.

## What the curve shows

Open **Statistics → Charging Curve**:

| Metric | Meaning |
|--------|---------|
| **Peak power** | Highest observed DC/AC power |
| **Average power** | Across the whole curve |
| **Total time** | Duration of analysed charging |
| **Time wasted (80–100%)** | Minutes spent filling the slow last 20% |
| **Power vs SoC** | Chart of charge power by battery percentage |

## How to read it

1. **Early SoC (10–30%)** — should be near your car’s max charge power  
2. **Mid SoC (30–60%)** — gradual taper is normal  
3. **High SoC (70–100%)** — power drops sharply; often not worth waiting for 100% on a road trip  

## Why it matters

- Compare public chargers (marketing vs real kW)
- Decide where to stop: arrive low, charge only to ~70–80%
- Spot degradation if the same charger gets slower over years

## Related tabs

- **Curve Integrals** — energy and time per SoC bracket  
- **Charging Stats** — sessions and cost  
- **Battery SoH** — uses charging taper as one health signal  

## Tips

- Prefer several DC sessions for a clean curve  
- Winter can lower peak power (cold pack)  
- Use the **Period** picker to include the sessions you care about
