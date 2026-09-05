"use client";

import { useSyncExternalStore } from "react";

/** A coarse clock (default 5 s) as an external store, so render stays pure. Server snapshot is 0. */
const subscribers = new Map<number, Set<() => void>>();
const timers = new Map<number, ReturnType<typeof setInterval>>();

function subscribeFor(stepMs: number) {
  return (cb: () => void) => {
    let set = subscribers.get(stepMs);
    if (!set) {
      set = new Set();
      subscribers.set(stepMs, set);
      timers.set(stepMs, setInterval(() => subscribers.get(stepMs)?.forEach((f) => f()), stepMs));
    }
    set.add(cb);
    return () => {
      set!.delete(cb);
      if (set!.size === 0) {
        clearInterval(timers.get(stepMs));
        timers.delete(stepMs);
        subscribers.delete(stepMs);
      }
    };
  };
}

const snapshotFor = (stepMs: number) => () => Math.floor(Date.now() / stepMs) * stepMs;
const serverSnapshot = () => 0;

export function useNow(stepMs = 5000): number {
  return useSyncExternalStore(subscribeFor(stepMs), snapshotFor(stepMs), serverSnapshot);
}

/** True after hydration; false during SSR and the hydration pass. */
const noop = () => () => {};
export function useMounted(): boolean {
  return useSyncExternalStore(noop, () => true, () => false);
}
