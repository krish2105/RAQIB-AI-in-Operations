import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";
import en from "@/messages/en.json";
import type { TwinReplay, TwinWhatIf } from "@/lib/api";
import { BINS, advance, binIndex, binLabel, clampBin, downsample, eventsAt, occupancyAt } from "@/lib/twin-math";
import { DeltaCard } from "@/components/twin/delta-card";
import { Scrubber } from "@/components/twin/scrubber";

const wrap = (ui: React.ReactNode) => render(<NextIntlClientProvider locale="en" messages={en}>{ui}</NextIntlClientProvider>);

const replay: TwinReplay = { site: "s", day: "2026-09-04", bins: BINS, arrivals: Array(BINS).fill(0), served: Array(BINS).fill(0), queue: Array(BINS).fill(0),
  occupancy: { entrance: Array(BINS).fill(0), queue_till_1: Array(BINS).fill(0) }, shelf: {}, events: [{ min: 600, id: "e1", kind: "queue_over", severity: 2, zone: "queue_till_1", rule_id: "R10" }], zones: [],
  totals: { events: 1, arrivals: 0, served: 0, queue_alerts: 1, shelf_gaps: 0, peak_queue: 6, busiest_minute: 600, shelf_availability: {} }, simulated_share: 1 };
replay.occupancy.queue_till_1[600] = 6; replay.occupancy.queue_till_1[601] = 6; replay.occupancy.queue_till_1[602] = 6;

describe("twin math", () => {
  it("clamps, labels and advances the playhead at speed", () => {
    expect(clampBin(-5)).toBe(0); expect(clampBin(9999)).toBe(BINS - 1); expect(binLabel(600)).toBe("10:00"); expect(binLabel(1439)).toBe("23:59");
    expect(clampBin(600.4)).toBe(600.4); expect(binIndex(600.6)).toBe(601); // fractional playhead, rounded index
    expect(advance(0, 1000, 60)).toBe(1);        // 60×: one real second = one replay minute
    expect(advance(100, 500, 600)).toBe(105);   // 600×: half a second = five minutes
    expect(downsample([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], 10)).toEqual([55, 11]);
  });
  it("reads occupancy and events at a bin with a small window", () => {
    expect(occupancyAt(replay, 601).queue_till_1).toBeCloseTo(18 / 5);
    expect(occupancyAt(replay, 0).entrance).toBe(0);
    expect(eventsAt(replay, 601).map((e) => e.id)).toEqual(["e1"]);
    expect(eventsAt(replay, 620)).toEqual([]);
  });
});

describe("Twin components", () => {
  it("scrubber range drives the bin and shows the clock", () => {
    const onBin = vi.fn();
    wrap(<Scrubber bin={600} onBin={onBin} arrivals={replay.arrivals} queue={replay.queue} events={replay.events} />);
    expect(screen.getByTestId("clock")).toHaveTextContent("10:00");
    fireEvent.change(screen.getByTestId("scrub-range"), { target: { value: "720" } });
    expect(onBin).toHaveBeenCalledWith(720);
  });
  it("delta card shows before/after and the wait reduction", () => {
    const k = (staff: number, wait: number) => ({ tills: [3], staff_hours: staff, customer_wait_min: wait, mean_wq_min: wait / 100, peak_rho: 0.9, service_level_model: 0.8, unstable_slots: 0, per_slot: [] });
    const w: TwinWhatIf = { site: "s", day: "2026-09-04", sufficient: true, slots: 96, slot_minutes: 15, mu_per_h: 30, mu_source: "estimated_from_video", baseline_tills: 3,
      inputs: { tills_by_slot: null, staff_delta: 1, zone_changes: {} }, before: k(72, 400), after: k(96, 250), milp: k(60, 300),
      delta: { staff_hours: 24, customer_wait_min: -150, wait_reduction_pct: 37.5, service_level_model: 0, peak_rho: -0.2 } };
    wrap(<DeltaCard w={w} />);
    expect(screen.getByTestId("delta-card")).toHaveTextContent("−37.5%");
    expect(screen.getByTestId("delta-card")).toHaveTextContent("+24");
    wrap(<DeltaCard w={{ site: "s", day: "d", sufficient: false }} />);
    expect(screen.getByText("No slots to model on this day.")).toBeInTheDocument();
  });
});
