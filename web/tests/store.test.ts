import { describe, expect, it } from "vitest";
import type { ApiEvent } from "@/lib/api";
import { LIVE_BUFFER, pushLive } from "@/lib/store";

const mk = (id: string): ApiEvent => ({ id, site: "s", camera: "c", ts: "2026-09-06T00:00:00Z", kind: "footfall_tick", severity: 1, payload: {}, clip_path: null, rule_id: "R12", received_at: "", handled: true, has_clip: false });

describe("live buffer reducer", () => {
  it("prepends newest and de-duplicates", () => {
    let s = { events: [], lastId: null } as { events: ApiEvent[]; lastId: string | null };
    s = pushLive(s, mk("a"));
    s = pushLive(s, mk("b"));
    const again = pushLive(s, mk("b"));
    expect(s.events.map((e) => e.id)).toEqual(["b", "a"]);
    expect(again).toBe(s);
  });
  it("caps at the buffer size", () => {
    let s = { events: [] as ApiEvent[], lastId: null as string | null };
    for (let i = 0; i < LIVE_BUFFER + 25; i++) s = pushLive(s, mk(String(i)));
    expect(s.events).toHaveLength(LIVE_BUFFER);
    expect(s.events[0].id).toBe(String(LIVE_BUFFER + 24));
  });
});
