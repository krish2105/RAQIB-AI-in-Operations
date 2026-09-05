import type { ApiEvent } from "@/lib/api";
import { TICK_KINDS } from "@/lib/severity";

export const BIN_MIN = 5;
export const BINS_PER_DAY = (24 * 60) / BIN_MIN; // 288

export interface Tick {
  id: string;
  x: number; // 0..1 across the day
  severity: number;
  kind: string;
  ts: string;
}

export interface TapeData {
  footfall: number[]; // length 288
  ticks: Tick[];
  max: number;
}

/** Bin index for a timestamp relative to the day start (ms). */
export function binIndex(tsMs: number, dayStartMs: number, binMin = BIN_MIN): number {
  const idx = Math.floor((tsMs - dayStartMs) / (binMin * 60_000));
  return Math.min(BINS_PER_DAY - 1, Math.max(0, idx));
}

export function binEvents(events: ApiEvent[], dayStart: Date, binMin = BIN_MIN): TapeData {
  const start = dayStart.getTime();
  const end = start + 86_400_000;
  const footfall = new Array<number>(BINS_PER_DAY).fill(0);
  const ticks: Tick[] = [];
  for (const e of events) {
    const t = new Date(e.ts).getTime();
    if (Number.isNaN(t) || t < start || t >= end) continue;
    if (e.kind === "footfall_tick") {
      footfall[binIndex(t, start, binMin)] += 1;
    } else if ((TICK_KINDS as string[]).includes(e.kind)) {
      ticks.push({ id: e.id, x: (t - start) / 86_400_000, severity: e.severity, kind: e.kind, ts: e.ts });
    }
  }
  ticks.sort((a, b) => a.x - b.x);
  return { footfall, ticks, max: Math.max(1, ...footfall) };
}

/** Light smoothing for the trace (3-bin moving average), keeps zeros as zeros at the ends. */
export function smooth(values: number[]): number[] {
  return values.map((v, i) => {
    const a = values[i - 1] ?? v;
    const b = values[i + 1] ?? v;
    return (a + v * 2 + b) / 4;
  });
}

/** Nearest tick to a normalised x within `tol` (normalised units). */
export function nearestTick(ticks: Tick[], x: number, tol: number): Tick | null {
  let best: Tick | null = null;
  let bestD = tol;
  for (const t of ticks) {
    const d = Math.abs(t.x - x);
    if (d <= bestD) {
      bestD = d;
      best = t;
    }
  }
  return best;
}
