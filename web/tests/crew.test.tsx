import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";
import en from "@/messages/en.json";
import type { CrewAgent, CrewMessage } from "@/lib/api";
import { AgentCard } from "@/components/crew/agent-card";
import { share } from "@/components/crew/budget-bar";
import { KillSwitch } from "@/components/crew/kill-switch";
import { buildGraph } from "@/components/crew/run-graph";

vi.mock("@/lib/api", async (orig) => {
  const mod = await orig<typeof import("@/lib/api")>();
  return { ...mod, api: { ...mod.api, crewStatus: vi.fn(async () => ({ agents_enabled: true, env_enabled: true, crew_enabled: true, flag: null })), crewKill: vi.fn(async () => ({ agents_enabled: false })) } };
});

const wrap = (ui: React.ReactNode) => render(<QueryClientProvider client={new QueryClient()}><NextIntlClientProvider locale="en" messages={en}>{ui}</NextIntlClientProvider></QueryClientProvider>);
const now = Date.now();
const floor: CrewAgent = { name: "FloorOps", role: "Queues", allowed_tools: ["propose_open_till", "send_alert"], triggers: ["queue_over"], budget: { max_tool_calls: 6, max_usd: 0, max_seconds: 60 }, runs: 3, flagged: 0, mandatory: false,
  last_run: { id: "r1", status: "ok", started: new Date(now - 10_000).toISOString(), tool_calls: 2, cost_usd: 0, seconds: 1.2 } };
const auditor: CrewAgent = { ...floor, name: "Auditor", role: "Check", allowed_tools: ["flag_run", "quarantine_memory"], triggers: ["after_every_run"], mandatory: true, last_run: { id: "r2", status: "ok", started: new Date(now - 120_000).toISOString(), tool_calls: 0, cost_usd: 0, seconds: 0.3 } };
const msgs: CrewMessage[] = [{ id: "m1", run_id: "r1", from: "FloorOps", to: "Auditor", schema: "run_report", payload: {}, hmac: "ab…", verified: true, ts: new Date(now - 5_000).toISOString() }];

describe("Crew", () => {
  it("budget share caps at 1 and treats a zero-dollar budget as breached by any spend", () => {
    expect(share(3, 6)).toBe(0.5); expect(share(9, 6)).toBe(1); expect(share(0, 0)).toBe(0); expect(share(0.01, 0)).toBe(1);
  });
  it("agent card lights when it ran in the last minute and shows mandatory + budgets", () => {
    wrap(<><AgentCard a={floor} /><AgentCard a={auditor} /></>);
    expect(screen.getByTestId("agent-FloorOps")).toHaveAttribute("data-lit", "true");
    expect(screen.getByTestId("agent-Auditor")).not.toHaveAttribute("data-lit");
    expect(screen.getByText("Mandatory")).toBeInTheDocument();
    expect(screen.getAllByTestId("budget-bar")).toHaveLength(6);
  });
  it("graph has one node per agent and animated edges for fresh signed messages", () => {
    const g = buildGraph([floor, auditor], msgs, now);
    expect(g.nodes.map((n) => n.id)).toEqual(["FloorOps", "Auditor"]);
    expect(g.edges).toHaveLength(1); expect(g.edges[0].animated).toBe(true); expect(g.edges[0].source).toBe("FloorOps");
  });
  it("kill switch needs the typed confirmation", async () => {
    const { api } = await import("@/lib/api");
    wrap(<KillSwitch site="s" />);
    const btn = await screen.findByTestId("kill-button");
    expect(btn).toBeDisabled();
    fireEvent.change(screen.getByTestId("kill-confirm"), { target: { value: "kill" } });
    expect(btn).toBeDisabled();
    fireEvent.change(screen.getByTestId("kill-confirm"), { target: { value: "KILL" } });
    expect(btn).not.toBeDisabled();
    fireEvent.click(btn);
    await vi.waitFor(() => expect(api.crewKill).toHaveBeenCalledWith("admin", "", "KILL"));
  });
});
