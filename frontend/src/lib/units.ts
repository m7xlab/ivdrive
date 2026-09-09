export type UnitSystem = "metric" | "uk" | "us" | "imperial";

const KM_PER_MI = 1.609344;

export function parseUnitSystem(value?: string | null): UnitSystem {
  if (value === "uk") return "uk";
  if (value === "us" || value === "imperial") return "us";
  return "metric";
}

export function usesMiles(system: UnitSystem): boolean {
  return system === "uk" || system === "us" || system === "imperial";
}

export function usesFahrenheit(system: UnitSystem): boolean {
  return system === "us" || system === "imperial";
}

export function kmToMiles(km: number): number {
  return km / KM_PER_MI;
}

export function milesToKm(miles: number): number {
  return miles * KM_PER_MI;
}

export function kmhToMph(kmh: number): number {
  return kmToMiles(kmh);
}

export function mphToKmh(mph: number): number {
  return milesToKm(mph);
}

export function cToF(celsius: number): number {
  return (celsius * 9) / 5 + 32;
}

export function fToC(fahrenheit: number): number {
  return ((fahrenheit - 32) * 5) / 9;
}

function round(value: number, places: number): number {
  const f = 10 ** places;
  return Math.round(value * f) / f;
}

export function formatDistance(
  km: number | null | undefined,
  system: UnitSystem = "metric",
  places = 0
): string {
  if (km == null || Number.isNaN(km)) return "--";
  const value = usesMiles(system) ? kmToMiles(km) : km;
  const formatted = round(value, places).toLocaleString(undefined, {
    minimumFractionDigits: places,
    maximumFractionDigits: places,
  });
  return `${formatted} ${usesMiles(system) ? "mi" : "km"}`;
}

export function formatSpeed(kmh: number | null | undefined, system: UnitSystem = "metric"): string {
  if (kmh == null || Number.isNaN(kmh)) return "--";
  if (usesMiles(system)) return `${round(kmhToMph(kmh), 0)} mph`;
  return `${round(kmh, 0)} km/h`;
}

export function formatTemp(celsius: number | null | undefined, system: UnitSystem = "metric"): string {
  if (celsius == null || Number.isNaN(celsius)) return "--";
  if (usesFahrenheit(system)) return `${round(cToF(celsius), 0)}°F`;
  return `${round(celsius, 0)}°C`;
}

export function distanceLabel(system: UnitSystem): string {
  return usesMiles(system) ? "mi" : "km";
}

export function speedLabel(system: UnitSystem): string {
  return usesMiles(system) ? "mph" : "km/h";
}

export function tempLabel(system: UnitSystem): string {
  return usesFahrenheit(system) ? "°F" : "°C";
}

/** Any quantity stored per 100 km (kWh, cost, litres). */
export function per100KmToDisplay(valuePer100km: number, system: UnitSystem): number {
  return usesMiles(system) ? valuePer100km * KM_PER_MI : valuePer100km;
}

export function kwhPer100kmToDisplay(kwh100km: number, system: UnitSystem): number {
  return per100KmToDisplay(kwh100km, system);
}

export function consumptionLabel(system: UnitSystem): string {
  return usesMiles(system) ? "kWh/100mi" : "kWh/100km";
}

export function per100Label(system: UnitSystem): string {
  return usesMiles(system) ? "100mi" : "100km";
}

export function formatConsumption(
  kwh100km: number | null | undefined,
  system: UnitSystem = "metric",
  places = 1
): string {
  if (kwh100km == null || Number.isNaN(kwh100km)) return "--";
  return `${round(kwhPer100kmToDisplay(kwh100km, system), places)} ${consumptionLabel(system)}`;
}
