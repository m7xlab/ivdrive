/** Full ECB daily list vs EUR — not a “who uses this app” subset. */
export const ECB_CURRENCIES: Array<{ code: string; name: string }> = [
  { code: "EUR", name: "Euro" },
  { code: "AUD", name: "Australian dollar" },
  { code: "BGN", name: "Bulgarian lev" },
  { code: "BRL", name: "Brazilian real" },
  { code: "CAD", name: "Canadian dollar" },
  { code: "CHF", name: "Swiss franc" },
  { code: "CNY", name: "Chinese yuan" },
  { code: "CZK", name: "Czech koruna" },
  { code: "DKK", name: "Danish krone" },
  { code: "GBP", name: "Pound sterling" },
  { code: "HKD", name: "Hong Kong dollar" },
  { code: "HUF", name: "Hungarian forint" },
  { code: "IDR", name: "Indonesian rupiah" },
  { code: "ILS", name: "Israeli shekel" },
  { code: "INR", name: "Indian rupee" },
  { code: "ISK", name: "Icelandic króna" },
  { code: "JPY", name: "Japanese yen" },
  { code: "KRW", name: "South Korean won" },
  { code: "MXN", name: "Mexican peso" },
  { code: "MYR", name: "Malaysian ringgit" },
  { code: "NOK", name: "Norwegian krone" },
  { code: "NZD", name: "New Zealand dollar" },
  { code: "PHP", name: "Philippine peso" },
  { code: "PLN", name: "Polish zloty" },
  { code: "RON", name: "Romanian leu" },
  { code: "SEK", name: "Swedish krona" },
  { code: "SGD", name: "Singapore dollar" },
  { code: "THB", name: "Thai baht" },
  { code: "TRY", name: "Turkish lira" },
  { code: "USD", name: "US dollar" },
  { code: "ZAR", name: "South African rand" },
];

const SYMBOLS: Record<string, string> = {
  EUR: "€",
  USD: "$",
  GBP: "£",
  CHF: "CHF",
  PLN: "zł",
  CZK: "Kč",
  SEK: "kr",
  NOK: "kr",
  DKK: "kr",
  HUF: "Ft",
  RON: "lei",
  BGN: "лв",
  ISK: "kr",
  TRY: "₺",
  JPY: "¥",
  AUD: "A$",
  CAD: "C$",
  CNY: "¥",
  HKD: "HK$",
  NZD: "NZ$",
  SGD: "S$",
  INR: "₹",
  BRL: "R$",
  KRW: "₩",
  MXN: "MX$",
  ZAR: "R",
  THB: "฿",
  IDR: "Rp",
  ILS: "₪",
  PHP: "₱",
  MYR: "RM",
};

export function currencySymbol(code?: string | null): string {
  const upper = (code || "EUR").toUpperCase();
  return SYMBOLS[upper] || upper;
}

export function fromEur(
  amountEur: number | null | undefined,
  rate: number,
  places = 2
): number | null {
  if (amountEur == null || Number.isNaN(amountEur)) return null;
  const safeRate = rate > 0 ? rate : 1;
  const value = amountEur * safeRate;
  const f = 10 ** places;
  return Math.round(value * f) / f;
}

export function toEur(
  amount: number | null | undefined,
  rate: number,
  places = 4
): number | null {
  if (amount == null || Number.isNaN(amount)) return null;
  const safeRate = rate > 0 ? rate : 1;
  const value = amount / safeRate;
  const f = 10 ** places;
  return Math.round(value * f) / f;
}

export function formatMoney(
  amount: number | null | undefined,
  code?: string | null,
  places = 2
): string {
  if (amount == null || Number.isNaN(amount)) return "--";
  const symbol = currencySymbol(code);
  const digits = Math.max(0, places);
  const formatted = Number(amount).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  if (symbol.length > 1) return `${formatted} ${symbol}`;
  return `${symbol}${formatted}`;
}

export function formatMoneyFromEur(
  amountEur: number | null | undefined,
  code?: string | null,
  rate = 1,
  places = 2
): string {
  return formatMoney(fromEur(amountEur, rate, places), code, places);
}
