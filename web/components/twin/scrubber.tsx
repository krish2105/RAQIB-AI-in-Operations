"use client";

import { Pause, Play } from "lucide-react";
import { useReducedMotion } from "motion/react";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { BINS, advance, binIndex, binLabel, downsample } from "@/lib/twin-math";
import { cn } from "@/lib/utils";

const SPEEDS = [10, 60, 240, 600];

export function Scrubber({ bin, onBin, arrivals, queue, events }: { bin: number; onBin: (b: number) => void; arrivals: number[]; queue: number[]; events: Array<{ min: number; severity: number; id: string }> }) {
  const t = useTranslations("twin");
  const reduce = useReducedMotion();
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(60);
  const last = useRef<number | null>(null);
  const binRef = useRef(bin);
  useEffect(() => {
    binRef.current = bin;
  }, [bin]);

  useEffect(() => {
    if (!playing || reduce) return;
    let raf = 0;
    const step = (now: number) => {
      if (last.current !== null) {
        const next = advance(binRef.current, now - last.current, speed);
        if (next >= BINS - 1) {
          onBin(BINS - 1);
          setPlaying(false);
          return;
        }
        onBin(next);
      }
      last.current = now;
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => {
      cancelAnimationFrame(raf);
      last.current = null;
    };
  }, [playing, speed, reduce, onBin]);

  const arr = downsample(arrivals);
  const max = Math.max(1, ...arr);
  return (
    <div className="flex flex-col gap-2" data-testid="scrubber">
      <div className="relative h-16 w-full overflow-hidden rounded-md bg-sunken" aria-hidden>
        <svg viewBox={`0 0 ${arr.length} 100`} preserveAspectRatio="none" className="absolute inset-0 size-full">
          {arr.map((v, i) => (
            <rect key={i} x={i} y={100 - (v / max) * 100} width={1} height={(v / max) * 100} className="fill-signal/50" />
          ))}
          {events.map((e) => (
            <rect key={e.id} x={e.min / 10} y={0} width={0.6} height={100} className={cn(e.severity === 3 ? "fill-critical" : e.severity === 2 ? "fill-warn" : "fill-info/60")} />
          ))}
          <rect x={bin / 10} y={0} width={0.8} height={100} className="fill-ink" />
        </svg>
      </div>
      <input type="range" min={0} max={BINS - 1} value={binIndex(bin)} onChange={(e) => onBin(Number(e.target.value))} aria-label={t("day")} className="w-full accent-[var(--signal)]" data-testid="scrub-range" />
      <div className="flex flex-wrap items-center gap-2 font-mono text-[0.75rem]">
        <button type="button" onClick={() => setPlaying((p) => !p)} disabled={!!reduce} className="inline-flex h-8 items-center gap-1.5 rounded-md border border-hairline-strong px-2 text-ink hover:bg-raised disabled:opacity-50" data-testid="play">
          {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />} {playing ? t("pause") : t("play")}
        </button>
        <span className="text-ink" data-testid="clock">{binLabel(bin)}</span>
        <span className="text-ink-faint">{t("queue")} {queue[binIndex(bin)]?.toFixed(0) ?? 0}</span>
        <span className="ms-auto text-ink-faint">{t("speed")}</span>
        {SPEEDS.map((s) => (
          <button key={s} type="button" onClick={() => setSpeed(s)} className={cn("h-7 rounded px-2", speed === s ? "bg-raised text-ink" : "text-ink-muted hover:text-ink")} aria-pressed={speed === s}>
            {s}×
          </button>
        ))}
        {reduce && <span className="basis-full text-[0.6875rem] text-ink-faint">{t("reducedMotion")}</span>}
      </div>
    </div>
  );
}
