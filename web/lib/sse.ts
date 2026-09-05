"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { api, type ApiEvent } from "./api";
import { useAppStore } from "./store";

/**
 * One EventSource per site. Pushes `event` messages into the live buffer and
 * invalidates the queries that depend on them. Reconnects with backoff and
 * reports state to the store so the header can show "reconnecting".
 */
export function useLiveStream(site: string) {
  const qc = useQueryClient();
  const pushEvent = useAppStore((s) => s.pushEvent);
  const setLive = useAppStore((s) => s.setLive);
  const attempt = useRef(0);

  useEffect(() => {
    if (!site || typeof window === "undefined" || typeof EventSource === "undefined") return;
    let es: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let closed = false;
    let invalidateTimer: ReturnType<typeof setTimeout> | null = null;

    const invalidateSoon = () => {
      if (invalidateTimer) return;
      invalidateTimer = setTimeout(() => {
        invalidateTimer = null;
        qc.invalidateQueries({ queryKey: ["kpis", site] });
        qc.invalidateQueries({ queryKey: ["events", site] });
        qc.invalidateQueries({ queryKey: ["actions", site] });
      }, 1500);
    };

    const connect = () => {
      if (closed) return;
      setLive(attempt.current === 0 ? "connecting" : "reconnecting");
      es = new EventSource(api.streamUrl(site));
      es.addEventListener("hello", () => {
        attempt.current = 0;
        setLive("live");
      });
      es.addEventListener("event", (m) => {
        try {
          const ev = JSON.parse((m as MessageEvent).data) as ApiEvent;
          pushEvent(ev);
          invalidateSoon();
        } catch {
          /* ignore malformed */
        }
      });
      es.addEventListener("action", () => invalidateSoon());
      es.addEventListener("clip", () => qc.invalidateQueries({ queryKey: ["events", site] }));
      es.onerror = () => {
        es?.close();
        setLive("reconnecting");
        attempt.current += 1;
        const delay = Math.min(30_000, 1000 * 2 ** Math.min(attempt.current, 5));
        timer = setTimeout(connect, delay);
      };
    };
    connect();
    return () => {
      closed = true;
      es?.close();
      if (timer) clearTimeout(timer);
      if (invalidateTimer) clearTimeout(invalidateTimer);
      setLive("off");
    };
  }, [site, qc, pushEvent, setLive]);
}
