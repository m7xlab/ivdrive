"use client";

import { useAuth } from "@/lib/auth-context";
import { currencySymbol, formatMoney, fromEur, toEur } from "@/lib/currency";
import {
  consumptionLabel,
  distanceLabel,
  formatConsumption,
  formatDistance,
  formatSpeed,
  formatTemp,
  kmToMiles,
  kwhPer100kmToDisplay,
  milesToKm,
  parseUnitSystem,
  per100KmToDisplay,
  per100Label,
  speedLabel,
  tempLabel,
  usesFahrenheit,
  usesMiles,
  type UnitSystem,
} from "@/lib/units";

export function useLocale() {
  const { user } = useAuth();
  const preferred = (user?.default_currency || "EUR").toUpperCase();
  const unitSystem: UnitSystem = parseUnitSystem(user?.unit_system);
  const hasRate = preferred === "EUR" || (user?.fx_rate != null && user.fx_rate > 0);
  const currency = hasRate ? preferred : "EUR";
  const fxRate = hasRate ? (user?.fx_rate && user.fx_rate > 0 ? user.fx_rate : 1) : 1;
  const fxAsOf = user?.fx_as_of || null;

  return {
    currency,
    unitSystem,
    fxRate,
    fxAsOf,
    fromEur: (amountEur: number | null | undefined, places = 2) => fromEur(amountEur, fxRate, places),
    toEur: (amount: number | null | undefined, places = 4) => toEur(amount, fxRate, places),
    formatMoneyFromEur: (amountEur: number | null | undefined, places = 2) =>
      formatMoney(fromEur(amountEur, fxRate, places), currency, places),
    formatDistance: (km: number | null | undefined, places = 0) =>
      formatDistance(km, unitSystem, places),
    formatSpeed: (kmh: number | null | undefined) => formatSpeed(kmh, unitSystem),
    formatTemp: (celsius: number | null | undefined) => formatTemp(celsius, unitSystem),
    formatConsumption: (kwh100km: number | null | undefined, places = 1) =>
      formatConsumption(kwh100km, unitSystem, places),
    kmToDisplay: (km: number) => (usesMiles(unitSystem) ? kmToMiles(km) : km),
    displayToKm: (value: number) => (usesMiles(unitSystem) ? milesToKm(value) : value),
    kwhPer100ToDisplay: (kwh100km: number) => kwhPer100kmToDisplay(kwh100km, unitSystem),
    per100ToDisplay: (valuePer100km: number) => per100KmToDisplay(valuePer100km, unitSystem),
    currencySymbol: currencySymbol(currency),
    distanceLabel: distanceLabel(unitSystem),
    speedLabel: speedLabel(unitSystem),
    tempLabel: tempLabel(unitSystem),
    consumptionLabel: consumptionLabel(unitSystem),
    per100Label: per100Label(unitSystem),
    usesMiles: usesMiles(unitSystem),
    usesFahrenheit: usesFahrenheit(unitSystem),
  };
}
