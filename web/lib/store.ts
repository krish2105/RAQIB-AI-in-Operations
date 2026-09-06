"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ApiEvent, DetectionFrame } from "./api";

export type Profile = "retail" | "factory";
export type LiveState = "connecting" | "live" | "reconnecting" | "off";

export const DEFAULT_SITE: Record<Profile, string> = {
  retail: "raqib_demo_store",
  factory: "greenlam_unit1",
};

export const LIVE_BUFFER = 200;

export interface LiveEventState {
  events: ApiEvent[];
  lastId: string | null;
}

/** Pure reducer for the live buffer: newest first, de-duplicated, capped. */
export function pushLive(state: LiveEventState, incoming: ApiEvent): LiveEventState {
  if (state.events.some((e) => e.id === incoming.id)) return state;
  const events = [incoming, ...state.events].slice(0, LIVE_BUFFER);
  return { events, lastId: incoming.id };
}

interface AppState {
  detections: Record<string, DetectionFrame>;
  pushDetections: (d: DetectionFrame) => void;
  site: string;
  profile: Profile;
  live: LiveState;
  buffer: LiveEventState;
  railCollapsed: boolean;
  setSite: (site: string, profile: Profile) => void;
  setLive: (s: LiveState) => void;
  pushEvent: (e: ApiEvent) => void;
  clearBuffer: () => void;
  toggleRail: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      detections: {},
      pushDetections: (d) => set((s) => ({ detections: { ...s.detections, [d.camera]: d } })),
      site: DEFAULT_SITE.retail,
      profile: "retail",
      live: "connecting",
      buffer: { events: [], lastId: null },
      railCollapsed: false,
      setSite: (site, profile) => set({ site, profile, buffer: { events: [], lastId: null }, detections: {} }),
      setLive: (live) => set({ live }),
      pushEvent: (e) => set((s) => ({ buffer: pushLive(s.buffer, e) })),
      clearBuffer: () => set({ buffer: { events: [], lastId: null } }),
      toggleRail: () => set((s) => ({ railCollapsed: !s.railCollapsed })),
    }),
    {
      name: "raqib-ui",
      partialize: (s) => ({ site: s.site, profile: s.profile, railCollapsed: s.railCollapsed }),
    },
  ),
);
