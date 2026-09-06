"use client";

import { cn } from "@/lib/utils";

/** Used share of a per-run budget, 0..1. Exported for tests. */
export function share(used: number, max: number) {
  if (max <= 0) return used > 0 ? 1 : 0;
  return Math.min(1, used / max);
}

export function BudgetBar({ label, used, max, unit }: { label: string; used: number; max: number; unit: string }) {
  const s = share(used, max);
  return (
    <div className="flex items-center gap-2 font-mono text-[0.6875rem]" data-testid="budget-bar">
      <span className="w-14 shrink-0 text-ink-faint">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-sunken" role="meter" aria-valuemin={0} aria-valuemax={max} aria-valuenow={used} aria-label={label}>
        <div className={cn("h-full rounded-full", s >= 1 ? "bg-critical" : s > 0.8 ? "bg-warn" : "bg-signal")} style={{ width: `${Math.round(s * 100)}%` }} />
      </div>
      <span className="w-16 shrink-0 text-end text-ink-muted">{used}/{max} {unit}</span>
    </div>
  );
}
