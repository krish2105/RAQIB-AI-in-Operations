"use client";

import { useLiveStream } from "@/lib/sse";
import { useAppStore } from "@/lib/store";

/** Mounts once per console; owns the SSE connection for the active site. */
export function LiveBoot() {
  const site = useAppStore((s) => s.site);
  useLiveStream(site);
  return null;
}
