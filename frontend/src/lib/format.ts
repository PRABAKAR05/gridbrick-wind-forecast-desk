/** Formatting helpers. All timestamps arrive as UTC and are rendered in the
 *  market's local timezone (Europe/London). */

const LONDON = "Europe/London";

const intFmt = new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 });
const oneFmt = new Intl.NumberFormat("en-GB", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});
const twoFmt = new Intl.NumberFormat("en-GB", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function fmtInt(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return intFmt.format(value);
}

export function fmt1(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return oneFmt.format(value);
}

export function fmt2(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return twoFmt.format(value);
}

export function fmtSigned(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const body = digits === 0 ? intFmt.format(Math.abs(value)) : oneFmt.format(Math.abs(value));
  return `${value > 0 ? "+" : value < 0 ? "−" : ""}${body}`;
}

/** MWh -> GWh with one decimal. */
export function fmtGwh(mwh: number | null | undefined): string {
  if (mwh === null || mwh === undefined || Number.isNaN(mwh)) return "—";
  return oneFmt.format(mwh / 1000);
}

export function fmtMwShort(mw: number | null | undefined): string {
  if (mw === null || mw === undefined || Number.isNaN(mw)) return "—";
  if (Math.abs(mw) >= 1000) return `${oneFmt.format(mw / 1000)} GW`;
  return `${intFmt.format(mw)} MW`;
}

export function fmtPct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(digits)}%`;
}

/** Accepts a 0-1 fraction. */
export function fmtFractionPct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(digits)}%`;
}

export function parseIso(value: string): Date {
  return new Date(value.endsWith("Z") ? value : `${value}Z`);
}

export function fmtDateLong(iso: string): string {
  const date = iso.includes("T") ? parseIso(iso) : new Date(`${iso}T12:00:00Z`);
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: LONDON,
  }).format(date);
}

export function fmtDateShort(iso: string): string {
  const date = iso.includes("T") ? parseIso(iso) : new Date(`${iso}T12:00:00Z`);
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    timeZone: LONDON,
  }).format(date);
}

export function fmtWeekday(iso: string): string {
  const date = iso.includes("T") ? parseIso(iso) : new Date(`${iso}T12:00:00Z`);
  return new Intl.DateTimeFormat("en-GB", { weekday: "short", timeZone: LONDON }).format(date);
}

export function fmtTime(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: LONDON,
  }).format(parseIso(iso));
}

export function fmtDateTime(iso: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: LONDON,
  }).format(parseIso(iso));
}

export function hourLabel(hour: number): string {
  return `${String(hour).padStart(2, "0")}:00`;
}

export function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

/** Move an ISO instant by whole hours, preserving the Z suffix. */
export function shiftIsoHours(iso: string, hours: number): string {
  const date = parseIso(iso);
  date.setUTCHours(date.getUTCHours() + hours);
  return date.toISOString();
}

export function isoToLocalInput(iso: string): string {
  const date = parseIso(iso);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

/** Convert a London wall-clock time on a calendar date into a UTC instant. */
export function londonWallTimeIso(date: string, hour: number, minute: number): string {
  const [year, month, day] = date.split("-").map(Number);
  const target = Date.UTC(year ?? 1970, (month ?? 1) - 1, day ?? 1, hour, minute);
  let guess = target;
  const formatter = new Intl.DateTimeFormat("en-GB", {
    timeZone: LONDON,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  });
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const parts = formatter.formatToParts(new Date(guess));
    const get = (type: string) => Number(parts.find((part) => part.type === type)?.value ?? 0);
    const wall = Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"));
    if (wall === target) break;
    guess += target - wall;
  }
  return new Date(guess).toISOString();
}
