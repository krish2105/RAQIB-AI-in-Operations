import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it } from "vitest";
import en from "@/messages/en.json";
import type { EdgeBox, FleetStore } from "@/lib/api";
import { EdgeHealth } from "@/components/fleet/edge-health";
import { Leaderboard, fmtKpi } from "@/components/fleet/leaderboard";

const wrap = (ui: React.ReactNode) => render(<NextIntlClientProvider locale="en" messages={en}>{ui}</NextIntlClientProvider>);
const store = (id: string, rank: number, sl: number | null): FleetStore => ({ rank, id, name: id.toUpperCase(), region: "Dubai", site_ids: [id], service_level: sl, osa: 0.97, compliance: null, agent_cost_usd: 0, events: 10 * rank, actions: 1, footfall: 100, edge: { boxes: 1, online: rank === 1 ? 1 : 0, offline: rank === 1 ? 0 : 1 } });

describe("Fleet", () => {
  it("formats KPIs by kind", () => {
    expect(fmtKpi("en", "service_level", 0.912)).toBe("91.2%");
    expect(fmtKpi("en", "agent_cost_usd", 0)).toBe("$0.0000");
    expect(fmtKpi("en", "events", 1234)).toBe("1,234");
    expect(fmtKpi("en", "osa", null)).toBe("–");
  });
  it("leaderboard renders ranks and edge status", () => {
    wrap(<Leaderboard stores={[store("a", 1, 0.95), store("b", 2, 0.8)]} kpi="service_level" />);
    expect(screen.getByTestId("store-a")).toHaveTextContent("95.0%");
    expect(screen.getByTestId("store-b")).toHaveTextContent("0/1");
  });
  it("edge box card shows status and model hash", () => {
    const box: EdgeBox = { box_id: "mac-1", status: "offline", last_seen: new Date(Date.now() - 400_000).toISOString(), gap_s: 400, fps: 17.2, temp_c: null, queue_depth: 3, model_hash: "abcdef012345", detector: "yolo", version: "0.2.0", cameras: ["cam1"], heartbeats_24h: 12, fps_24h: [{ ts: "", fps: 17, queue_depth: 0 }] };
    wrap(<EdgeHealth box={box} />);
    expect(screen.getByTestId("box-mac-1")).toHaveAttribute("data-status", "offline");
    expect(screen.getByText("offline")).toBeInTheDocument();
    expect(screen.getByText("yolo abcdef012345")).toBeInTheDocument();
  });
});
