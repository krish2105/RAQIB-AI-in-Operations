/** Pure helpers for the Twin scrubber. Exported for tests. */
import type { TwinReplay } from "./api";

export const BINS = 1440;

/** The playhead is fractional (a 16 ms frame at 60× is 0.016 of a minute); indexes round. */
export const clampBin = (b: number) => Math.max(0, Math.min(BINS - 1, b));
export const binIndex = (b: number) => Math.round(clampBin(b));

export const binLabel = (b: number) => `${String(Math.floor(binIndex(b) / 60)).padStart(2, "0")}:${String(binIndex(b) % 60).padStart(2, "0")}`;

/** Advance the playhead by wall-clock ms at `speed` × real time (60× means one real second = one replay minute). */
export const advance = (bin: number, dtMs: number, speed: number) => bin + (dtMs / 60_000) * speed;

/** Occupancy per zone at a bin, smoothed over a small window so slabs don't flicker. */
export function occupancyAt(r: TwinReplay, bin: number, window = 2): Record<string, number> {
  const b = binIndex(bin);
  const out: Record<string, number> = {};
  for (const [zone, series] of Object.entries(r.occupancy)) {
    let s = 0;
    let n = 0;
    for (let i = Math.max(0, b - window); i <= Math.min(BINS - 1, b + window); i++) {
      s += series[i] ?? 0;
      n++;
    }
    out[zone] = n ? s / n : 0;
  }
  return out;
}

export const eventsAt = (r: TwinReplay, bin: number, window = 1) => r.events.filter((e) => Math.abs(e.min - binIndex(bin)) <= window);

/** Ten-minute series for the mini charts (144 points). */
export function downsample(series: number[], factor = 10): number[] {
  const out: number[] = [];
  for (let i = 0; i < series.length; i += factor) out.push(series.slice(i, i + factor).reduce((a, b) => a + b, 0));
  return out;
}
