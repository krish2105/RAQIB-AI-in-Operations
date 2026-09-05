"use client";

import { animate, motion, useMotionValue, useReducedMotion, useTransform } from "motion/react";
import { useEffect } from "react";
import { cn } from "@/lib/utils";

interface KpiTileProps {
  label: string;
  value: number | null | undefined;
  format: (n: number) => string;
  sub?: string;
  tone?: "neutral" | "signal" | "warn" | "critical" | "ok";
  hero?: boolean;
  loading?: boolean;
  target?: { value: number; met: boolean } | null;
}

export function KpiTile({ label, value, format, sub, tone = "neutral", hero, loading, target }: KpiTileProps) {
  const toneCls = {
    neutral: "text-ink",
    signal: "text-signal",
    warn: "text-warn",
    critical: "text-critical",
    ok: "text-ok",
  }[tone];
  return (
    <article className={cn("panel relative flex min-h-[120px] flex-col justify-between gap-3 p-4", hero && "sm:col-span-2")}>
      <div className="flex items-start justify-between gap-2">
        <span className="eyebrow">{label}</span>
        {target && (
          <span className={cn("font-mono text-[0.625rem] tracking-wide", target.met ? "text-ok" : "text-warn")} aria-label={`target ${format(target.value)}`}>
            {target.met ? "✓" : "↑"} {format(target.value)}
          </span>
        )}
      </div>
      <div className="flex items-end justify-between gap-3">
        <div className={cn("num leading-none", hero ? "display-wide text-[clamp(2.5rem,2rem+2vw,4rem)] font-semibold" : "text-[clamp(1.75rem,1.4rem+1vw,2.5rem)] font-medium", toneCls)}>
          {loading || value === null || value === undefined ? <span className="text-ink-faint">–</span> : <CountUp to={value} format={format} />}
        </div>
      </div>
      {sub && <p className="text-xs leading-snug text-ink-muted">{sub}</p>}
    </article>
  );
}

export function CountUp({ to, format, duration = 0.9 }: { to: number; format: (n: number) => string; duration?: number }) {
  const reduce = useReducedMotion();
  const mv = useMotionValue(reduce ? to : 0);
  const text = useTransform(mv, (v) => format(v));
  useEffect(() => {
    if (reduce) {
      mv.set(to);
      return;
    }
    const controls = animate(mv, to, { duration, ease: [0.16, 1, 0.3, 1] });
    return () => controls.stop();
  }, [to, mv, reduce, duration]);
  return <motion.span className="tabular-nums">{text}</motion.span>;
}
