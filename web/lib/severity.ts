import type { EventKind, Severity } from "./api";

export interface SeverityMeta {
  level: Severity;
  key: "info" | "warn" | "critical";
  token: "--info" | "--warn" | "--critical";
  cssClass: "sev-1" | "sev-2" | "sev-3";
  icon: "Info" | "TriangleAlert" | "OctagonAlert";
}

const META: Record<Severity, SeverityMeta> = {
  1: { level: 1, key: "info", token: "--info", cssClass: "sev-1", icon: "Info" },
  2: { level: 2, key: "warn", token: "--warn", cssClass: "sev-2", icon: "TriangleAlert" },
  3: { level: 3, key: "critical", token: "--critical", cssClass: "sev-3", icon: "OctagonAlert" },
};

export function severityMeta(level: number): SeverityMeta {
  const s = (level >= 3 ? 3 : level <= 1 ? 1 : 2) as Severity;
  return META[s];
}

/** Which event kinds are "operational signals" worth a tick on the tape (footfall is the trace itself). */
export const TICK_KINDS: EventKind[] = ["ppe_violation", "zone_breach", "machine_stopped", "queue_over", "shelf_gap", "price_mismatch", "planogram_drift"];

export const KIND_ICON: Record<EventKind, string> = {
  ppe_violation: "HardHat",
  zone_breach: "ShieldAlert",
  machine_stopped: "Cog",
  queue_over: "Users",
  shelf_gap: "PackageOpen",
  footfall_tick: "Footprints",
  checkout_served: "Receipt",
  price_mismatch: "Tag",
  planogram_drift: "LayoutGrid",
};

export function isProposal(tool: string): boolean {
  return tool.startsWith("propose_");
}
