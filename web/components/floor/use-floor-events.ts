"use client";

import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { api, type ApiEvent } from "@/lib/api";
import { TICK_KINDS } from "@/lib/severity";
import { useAppStore } from "@/lib/store";
import { useNow } from "@/lib/use-now";

export interface Pulse {
  id: string;
  zone: string;
  severity: number;
  at: number; // ms
}

/** Which floor zone an event belongs to (payload.zone, else by kind heuristics). */
export function zoneOf(e: ApiEvent): string | null {
  const z = e.payload?.zone;
  if (typeof z === "string") return z;
  if (e.kind === "footfall_tick") return "entrance";
  return null;
}

export function useFloorEvents(site: string, windowMs = 60_000) {
  const live = useAppStore((s) => s.buffer.events);
  const now = useNow(5000);
  const recent = useQuery({
    queryKey: ["events", site, "floor"],
    queryFn: () => api.events({ site, limit: 300 }),
    enabled: !!site,
    refetchInterval: 30_000,
  });
  return useMemo(() => {
    const all = new Map<string, ApiEvent>();
    for (const e of recent.data ?? []) all.set(e.id, e);
    for (const e of live) all.set(e.id, e);
    const lastByZone: Record<string, ApiEvent> = {};
    const pulses: Pulse[] = [];
    for (const e of all.values()) {
      const zone = zoneOf(e);
      if (!zone) continue;
      if ((TICK_KINDS as string[]).includes(e.kind)) {
        const prev = lastByZone[zone];
        if (!prev || prev.ts < e.ts) lastByZone[zone] = e;
      }
      const at = new Date(e.ts).getTime();
      if (now - at < windowMs && e.kind !== "checkout_served") pulses.push({ id: e.id, zone, severity: e.severity, at });
    }
    // If nothing is live, replay the last few ticks as pulses so the floor is never dead on first load.
    if (pulses.length === 0) {
      const latest = [...all.values()].filter((e) => (TICK_KINDS as string[]).includes(e.kind)).sort((a, b) => (a.ts < b.ts ? 1 : -1)).slice(0, 4);
      latest.forEach((e, i) => pulses.push({ id: e.id, zone: zoneOf(e) ?? "entrance", severity: e.severity, at: now - i * 4000 }));
    }
    return { lastByZone, pulses };
  }, [recent.data, live, windowMs, now]);
}
