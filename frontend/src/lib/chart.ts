/** Small, dependency-free chart maths. */

export type Domain = [number, number];

export interface Scale {
  (value: number): number;
  domain: Domain;
  range: Domain;
}

export function scaleLinear(domain: Domain, range: Domain): Scale {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const span = d1 - d0;
  const k = span === 0 ? 0 : (r1 - r0) / span;
  const fn = ((value: number) => r0 + (value - d0) * k) as Scale;
  fn.domain = domain;
  fn.range = range;
  return fn;
}

/** Human-friendly ticks (1/2/5 x 10^n stepping). */
export function ticks(min: number, max: number, count = 5): number[] {
  const span = max - min;
  if (!Number.isFinite(span) || span <= 0) return [min];
  const rough = span / Math.max(1, count);
  const magnitude = Math.pow(10, Math.floor(Math.log10(rough)));
  const normalised = rough / magnitude;
  const step = (normalised >= 7.5 ? 10 : normalised >= 3.5 ? 5 : normalised >= 1.5 ? 2 : 1) * magnitude;
  const start = Math.ceil(min / step) * step;
  const out: number[] = [];
  for (let value = start; value <= max + step * 1e-6; value += step) {
    out.push(Number(value.toPrecision(12)));
  }
  return out;
}

export function niceDomain(min: number, max: number, pad = 0.06): Domain {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
  if (min === max) {
    const delta = Math.abs(min) * 0.1 || 1;
    return [min - delta, max + delta];
  }
  const span = max - min;
  return [min - span * pad, max + span * pad];
}

export function path(points: readonly (readonly [number, number])[]): string {
  const valid = points.filter((p) => Number.isFinite(p[0]) && Number.isFinite(p[1]));
  if (!valid.length) return "";
  return valid
    .map(([x, y], index) => `${index === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`)
    .join(" ");
}

/** Closed area between an upper and a lower edge. */
export function bandPath(
  upper: readonly (readonly [number, number])[],
  lower: readonly (readonly [number, number])[],
): string {
  const top = path(upper);
  if (!top) return "";
  const bottom = [...lower]
    .reverse()
    .filter((p) => Number.isFinite(p[0]) && Number.isFinite(p[1]))
    .map(([x, y]) => `L${x.toFixed(2)},${y.toFixed(2)}`)
    .join(" ");
  return `${top} ${bottom} Z`;
}

/** Step path: holds each value until the next x. Good for hourly blocks. */
export function stepPath(points: readonly (readonly [number, number])[], stepWidth: number): string {
  if (!points.length) return "";
  let out = `M${points[0]![0].toFixed(2)},${points[0]![1].toFixed(2)}`;
  for (let i = 1; i < points.length; i += 1) {
    const [x, y] = points[i]!;
    out += ` L${x.toFixed(2)},${points[i - 1]![1].toFixed(2)} L${x.toFixed(2)},${y.toFixed(2)}`;
  }
  const last = points[points.length - 1]!;
  out += ` L${(last[0] + stepWidth).toFixed(2)},${last[1].toFixed(2)}`;
  return out;
}

export function extent(values: readonly (number | null | undefined)[]): Domain {
  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;
  for (const value of values) {
    if (value === null || value === undefined || !Number.isFinite(value)) continue;
    if (value < min) min = value;
    if (value > max) max = value;
  }
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];
  return [min, max];
}

/** Diverging colour for signed values, used by the error heatmap. */
export function diverging(value: number, scale: number): string {
  if (!Number.isFinite(value)) return "transparent";
  const t = Math.min(1, Math.abs(value) / (scale || 1));
  const alpha = 0.08 + t * 0.72;
  return value >= 0 ? `rgba(255,107,107,${alpha.toFixed(3)})` : `rgba(94,168,255,${alpha.toFixed(3)})`;
}

export function sequential(value: number, max: number): string {
  const t = Math.min(1, Math.max(0, value / (max || 1)));
  return `rgba(255,176,32,${(0.06 + t * 0.8).toFixed(3)})`;
}
