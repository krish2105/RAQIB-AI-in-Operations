"use client";

/**
 * The tape — a rolling 24-hour strip chart across the top of every page.
 * Like a flight recorder: the pen (now) is fixed at the trailing edge and the
 * paper moves under it. Footfall per 5-minute bin is the trace; operational
 * events are ticks coloured by severity. Hover scrubs, click a tick opens the
 * event. Canvas 2D, redrawn on data/theme/resize, and the window advances one
 * bin every 5 minutes (frozen under prefers-reduced-motion).
 */

import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useReducedMotion } from "motion/react";
import { useTheme } from "next-themes";
import { useRouter } from "@/i18n/navigation";
import { api } from "@/lib/api";
import { fmtNumber, fmtTime, tzOffsetMinutes } from "@/lib/format";
import { useAppStore } from "@/lib/store";
import { useNow } from "@/lib/use-now";
import { BIN_MIN, binEvents, nearestTick, smooth, type Tick } from "./tape-math";

const H = 84;
const DAY_MS = 86_400_000;
const BIN_MS = BIN_MIN * 60_000;

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

export function Tape() {
  const t = useTranslations("tape");
  const tk = useTranslations("kind");
  const locale = useLocale();
  const router = useRouter();
  const reduce = useReducedMotion();
  const { resolvedTheme } = useTheme();
  const site = useAppStore((s) => s.site);
  const profile = useAppStore((s) => s.profile);
  const live = useAppStore((s) => s.buffer.events);
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [hover, setHover] = useState<{ x: number; px: number; tick: Tick | null; bin: number } | null>(null);
  // Window end = now rounded up to the next 5-min bin; advances once per bin.
  const nowBin = useNow(BIN_MS);
  const end = useMemo(() => Math.ceil(nowBin / BIN_MS) * BIN_MS, [nowBin]); // 0 during SSR
  const start = useMemo(() => new Date(end - DAY_MS), [end]);
  const since = start.toISOString();
  const today = useQuery({
    queryKey: ["events", site, "tape", since],
    queryFn: () => api.events({ site, since, limit: 5000 }),
    enabled: !!site && nowBin > 0,
    refetchInterval: 60_000,
  });

  const data = useMemo(() => {
    const merged = new Map<string, (typeof live)[number]>();
    for (const e of today.data ?? []) merged.set(e.id, e);
    for (const e of live) merged.set(e.id, e);
    return binEvents([...merged.values()], start);
  }, [today.data, live, start]);

  // Hour marks: every 3 h of *local* clock time inside the window.
  const hourMarks = useMemo(() => {
    const offset = tzOffsetMinutes(start) * 60_000;
    const localStart = start.getTime() + offset;
    const firstLocalHour = Math.ceil(localStart / 3_600_000) * 3_600_000;
    const marks: Array<{ x: number; label: string }> = [];
    for (let t = firstLocalHour; t <= localStart + DAY_MS; t += 3_600_000) {
      const localHour = Math.round(((t / 3_600_000) % 24 + 24) % 24);
      if (localHour % 3 !== 0) continue;
      marks.push({ x: (t - localStart) / DAY_MS, label: `${String(localHour).padStart(2, "0")}:00` });
    }
    return marks;
  }, [start]);

  const draw = useCallback(() => {
    const el = canvas.current;
    const box = wrap.current;
    if (!el || !box) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const W = box.clientWidth;
    el.width = Math.floor(W * dpr);
    el.height = Math.floor(H * dpr);
    el.style.width = `${W}px`;
    el.style.height = `${H}px`;
    const ctx = el.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);

    const signal = cssVar("--signal");
    const hair = cssVar("--hairline-strong");
    const inkMuted = cssVar("--ink-muted");
    const ink = cssVar("--ink");
    const sev = { 1: cssVar("--info"), 2: cssVar("--warn"), 3: cssVar("--critical") } as Record<number, string>;
    const rtl = document.documentElement.dir === "rtl";
    const X = (frac: number) => (rtl ? W - frac * W : frac * W);

    // hour grid (local clock, every 3 h, scrolling with the window)
    ctx.strokeStyle = hair;
    ctx.lineWidth = 1;
    ctx.font = `500 10px ${cssVar("--font-mono") || "monospace"}`;
    ctx.fillStyle = inkMuted;
    ctx.textBaseline = "top";
    for (const m of hourMarks) {
      const x = Math.round(X(m.x)) + 0.5;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, H - 14);
      ctx.stroke();
      if (m.x < 0.97) {
        ctx.textAlign = rtl ? "right" : "left";
        ctx.fillText(m.label, x + (rtl ? -4 : 4), H - 12);
      }
    }

    // footfall trace (area + line)
    const traceH = H - 22;
    const base = 4 + traceH;
    const vals = smooth(data.footfall);
    const max = Math.max(3, data.max);
    ctx.beginPath();
    ctx.moveTo(X(0), base);
    vals.forEach((v, i) => {
      const x = X((i + 0.5) / vals.length);
      const y = base - (v / max) * traceH;
      ctx.lineTo(x, y);
    });
    ctx.lineTo(X(1), base);
    ctx.closePath();
    ctx.fillStyle = signal;
    ctx.globalAlpha = 0.16;
    ctx.fill();
    ctx.globalAlpha = 1;
    ctx.beginPath();
    vals.forEach((v, i) => {
      const x = X((i + 0.5) / vals.length);
      const y = base - (v / max) * traceH;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = signal;
    ctx.lineWidth = 1.25;
    ctx.stroke();

    // ticks
    for (const tk of data.ticks) {
      const x = Math.round(X(tk.x)) + 0.5;
      const h = tk.severity === 3 ? traceH : tk.severity === 2 ? traceH * 0.62 : traceH * 0.34;
      ctx.strokeStyle = sev[tk.severity] ?? sev[1];
      ctx.lineWidth = tk.severity === 3 ? 2 : 1.25;
      ctx.beginPath();
      ctx.moveTo(x, base);
      ctx.lineTo(x, base - h);
      ctx.stroke();
      if (tk.severity === 3) {
        ctx.fillStyle = sev[3];
        ctx.beginPath();
        ctx.arc(x, base - h, 2.5, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // the pen: fixed at the trailing edge
    const frac = Math.min(1, Math.max(0, (Date.now() - start.getTime()) / DAY_MS));
    const px = Math.round(X(frac)) + 0.5;
    ctx.strokeStyle = ink;
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 3]);
    ctx.beginPath();
    ctx.moveTo(px, 0);
    ctx.lineTo(px, base);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = ink;
    ctx.beginPath();
    ctx.moveTo(px - 4, 0);
    ctx.lineTo(px + 4, 0);
    ctx.lineTo(px, 5);
    ctx.closePath();
    ctx.fill();

    // hover hairline
    if (hover) {
      ctx.strokeStyle = inkMuted;
      ctx.beginPath();
      ctx.moveTo(hover.px + 0.5, 0);
      ctx.lineTo(hover.px + 0.5, base);
      ctx.stroke();
    }
  }, [data, hover, start, hourMarks]);

  useEffect(() => {
    draw();
  }, [draw, resolvedTheme, profile]);

  // Redraw the pen every 30 s so it creeps between bin advances (skipped under reduced motion).
  useEffect(() => {
    if (reduce) return;
    const id = setInterval(draw, 30_000);
    return () => clearInterval(id);
  }, [draw, reduce]);

  useEffect(() => {
    const ro = new ResizeObserver(() => draw());
    if (wrap.current) ro.observe(wrap.current);
    return () => ro.disconnect();
  }, [draw]);

  const onMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const rtl = document.documentElement.dir === "rtl";
    const pxRaw = e.clientX - r.left;
    const frac = rtl ? 1 - pxRaw / r.width : pxRaw / r.width;
    const tol = 6 / r.width;
    setHover({ x: frac, px: pxRaw, tick: nearestTick(data.ticks, frac, tol), bin: Math.floor(frac * data.footfall.length) });
  };
  const onClick = () => {
    if (hover?.tick) router.push(`/events/${hover.tick.id}`);
  };

  const total = data.ticks.length;
  const hoverTime = hover ? fmtTime(locale, new Date(start.getTime() + hover.x * DAY_MS)) : null;

  return (
    <section aria-label={t("title")} className="relative border-b border-hairline bg-sunken/60">
      <div className="mx-auto flex max-w-[1600px] items-center justify-between px-3 pt-2 sm:px-5">
        <div className="flex items-baseline gap-3">
          <span className="eyebrow">{t("title")}</span>
          <span className="font-mono text-[0.6875rem] text-ink-faint">{t("events", { count: total })}</span>
        </div>
        <span className="hidden font-mono text-[0.6875rem] text-ink-faint sm:inline">{t("hint")}</span>
      </div>
      <div ref={wrap} className="relative mx-auto max-w-[1600px] px-3 sm:px-5">
        <canvas
          ref={canvas}
          role="img"
          aria-label={`${t("title")}: ${t("events", { count: total })}`}
          className="block w-full cursor-crosshair"
          style={{ height: H }}
          onPointerMove={onMove}
          onPointerLeave={() => setHover(null)}
          onClick={onClick}
        />
        {hover && (
          <div
            role="tooltip"
            className="pointer-events-none absolute top-1 z-10 -translate-x-1/2 rounded-md border border-hairline bg-surface px-2 py-1 font-mono text-[0.6875rem] text-ink shadow-lg"
            style={{ left: `calc(${hover.px}px + ${document.documentElement.dir === "rtl" ? "0px" : "0px"})`, insetInlineStart: undefined }}
          >
            <span className="text-ink-muted">{hoverTime}</span>
            <span className="mx-2 text-signal">{fmtNumber(locale, data.footfall[hover.bin] ?? 0)}</span>
            <span className="text-ink-faint">{t("footfall")}</span>
            {hover.tick && (
              <span className={`ms-2 ${hover.tick.severity === 3 ? "text-critical" : hover.tick.severity === 2 ? "text-warn" : "text-info"}`}>
                · {tk(hover.tick.kind as Parameters<typeof tk>[0])}
              </span>
            )}
          </div>
        )}
        {today.isSuccess && total === 0 && data.max <= 1 && (
          <p className="pointer-events-none absolute inset-x-0 top-6 text-center text-xs text-ink-faint">{t("noEvents")}</p>
        )}
      </div>
    </section>
  );
}
