import { describe, expect, it } from "vitest";
import { isProposal, severityMeta, TICK_KINDS } from "@/lib/severity";

describe("severityMeta", () => {
  it("maps 3 to critical with the critical token and icon", () => {
    const m = severityMeta(3);
    expect(m).toMatchObject({ level: 3, key: "critical", token: "--critical", cssClass: "sev-3", icon: "OctagonAlert" });
  });
  it("clamps out-of-range values", () => {
    expect(severityMeta(0).level).toBe(1);
    expect(severityMeta(9).level).toBe(3);
    expect(severityMeta(2).cssClass).toBe("sev-2");
  });
  it("footfall is the trace, never a tick", () => {
    expect(TICK_KINDS).not.toContain("footfall_tick");
    expect(TICK_KINDS).toContain("queue_over");
  });
  it("proposal tools are recognised by prefix", () => {
    expect(isProposal("propose_open_till")).toBe(true);
    expect(isProposal("escalate")).toBe(false);
  });
});
