import { describe, expect, it } from "vitest";
import { binEvents, binIndex, BINS_PER_DAY, nearestTick, smooth } from "@/components/tape/tape-math";
import type { ApiEvent } from "@/lib/api";

const day = new Date("2026-09-06T00:00:00Z");
const ev = (ts: string, kind: ApiEvent["kind"], severity: 1 | 2 | 3 = 1, id = ts + kind): ApiEvent => ({
  id, site: "s", camera: "cam1", ts, kind, severity, payload: {}, clip_path: null, rule_id: "R", received_at: ts, handled: true, has_clip: false,
});

describe("tape binning", () => {
  it("puts 00:07 into bin 1 and 23:59 into the last bin", () => {
    expect(binIndex(new Date("2026-09-06T00:07:00Z").getTime(), day.getTime())).toBe(1);
    expect(binIndex(new Date("2026-09-06T23:59:59Z").getTime(), day.getTime())).toBe(BINS_PER_DAY - 1);
  });
  it("counts footfall per bin and turns operational events into ticks with ids", () => {
    const d = binEvents(
      [ev("2026-09-06T09:01:00Z", "footfall_tick"), ev("2026-09-06T09:03:00Z", "footfall_tick"), ev("2026-09-06T12:00:00Z", "queue_over", 2, "Q1"), ev("2026-09-06T18:30:00Z", "zone_breach", 3, "Z1"), ev("2026-09-05T18:30:00Z", "zone_breach", 3, "OLD"), ev("2026-09-06T10:00:00Z", "checkout_served")],
      day,
    );
    expect(d.footfall[binIndex(new Date("2026-09-06T09:01:00Z").getTime(), day.getTime())]).toBe(2);
    expect(d.footfall.reduce((a, b) => a + b, 0)).toBe(2);
    expect(d.ticks.map((t) => t.id)).toEqual(["Q1", "Z1"]);
    expect(d.ticks[0].x).toBeCloseTo(0.5, 5);
    expect(d.max).toBe(2);
  });
  it("smooth keeps length and total roughly", () => {
    const s = smooth([0, 4, 0, 0]);
    expect(s).toHaveLength(4);
    expect(s[1]).toBe(2);
  });
  it("nearestTick respects tolerance", () => {
    const ticks = [{ id: "a", x: 0.5, severity: 2, kind: "queue_over", ts: "" }];
    expect(nearestTick(ticks, 0.502, 0.01)?.id).toBe("a");
    expect(nearestTick(ticks, 0.6, 0.01)).toBeNull();
  });
});
