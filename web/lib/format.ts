/**
 * Locale-aware formatting. Digits stay Latin in every language (`nu-latn`):
 * a control room reads numbers across scripts, and tabular Latin digits keep
 * columns aligned. This is a deliberate choice, not an omission.
 */

const TZ = "Asia/Dubai";

function tag(locale: string) {
  return `${locale}-u-nu-latn`;
}

export function fmtNumber(locale: string, n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "–";
  return new Intl.NumberFormat(tag(locale), { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(n);
}

export function fmtPct(locale: string, x: number | null | undefined, digits = 1): string {
  if (x === null || x === undefined || Number.isNaN(x)) return "–";
  return new Intl.NumberFormat(tag(locale), { style: "percent", maximumFractionDigits: digits, minimumFractionDigits: digits }).format(x);
}

export function fmtTime(locale: string, iso: string | Date, withSeconds = false): string {
  const d = typeof iso === "string" ? new Date(iso) : iso;
  return new Intl.DateTimeFormat(tag(locale), { hour: "2-digit", minute: "2-digit", second: withSeconds ? "2-digit" : undefined, hour12: false, timeZone: TZ }).format(d);
}

export function fmtDate(locale: string, iso: string | Date): string {
  const d = typeof iso === "string" ? new Date(iso) : iso;
  return new Intl.DateTimeFormat(tag(locale), { day: "2-digit", month: "short", timeZone: TZ }).format(d);
}

export function fmtDateTime(locale: string, iso: string | Date): string {
  return `${fmtDate(locale, iso)} ${fmtTime(locale, iso, true)}`;
}

export function fmtRelative(locale: string, iso: string, now = Date.now()): string {
  const diff = (new Date(iso).getTime() - now) / 1000;
  const rtf = new Intl.RelativeTimeFormat(tag(locale), { numeric: "auto" });
  const abs = Math.abs(diff);
  if (abs < 60) return rtf.format(Math.round(diff), "second");
  if (abs < 3600) return rtf.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(diff / 3600), "hour");
  return rtf.format(Math.round(diff / 86400), "day");
}

export function fmtMinutes(locale: string, m: number | null | undefined): string {
  if (m === null || m === undefined) return "–";
  if (m < 1) return `${fmtNumber(locale, m * 60)} s`;
  return `${fmtNumber(locale, m, 1)} min`;
}

/** Start of the current day in the site timezone, as a Date. */
export function dayStart(now = new Date()): Date {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(now);
  const get = (t: string) => parts.find((p) => p.type === t)?.value;
  // Build the local midnight, then find its UTC equivalent by measuring the tz offset at that instant.
  const guess = new Date(`${get("year")}-${get("month")}-${get("day")}T00:00:00Z`);
  const offsetMin = tzOffsetMinutes(guess);
  return new Date(guess.getTime() - offsetMin * 60_000);
}

export function tzOffsetMinutes(at: Date): number {
  const dtf = new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour12: false, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" });
  const p = Object.fromEntries(dtf.formatToParts(at).map((x) => [x.type, x.value]));
  const asUtc = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour % 24, +p.minute, +p.second);
  return (asUtc - at.getTime()) / 60_000;
}

export const TIMEZONE = TZ;
