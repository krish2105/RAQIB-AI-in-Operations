"use client";

import { useQuery } from "@tanstack/react-query";
import { Activity, Cog, Footprints, HardHat, LayoutGrid, PackageOpen, Receipt, ShieldAlert, Tag, Users, Video, WifiOff } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo } from "react";
import { Link } from "@/i18n/navigation";
import { api, type ApiEvent, type EventKind } from "@/lib/api";
import { dayStart, fmtDate, fmtTime } from "@/lib/format";

function isToday(iso: string): boolean {
  return new Date(iso).getTime() >= dayStart().getTime();
}
import { useAppStore } from "@/lib/store";
import { EmptyState, ErrorState, SevChip, Skeleton } from "@/components/ui/panel";
import { cn } from "@/lib/utils";

const ICONS: Record<EventKind, React.ComponentType<{ className?: string; strokeWidth?: number }>> = {
  ppe_violation: HardHat,
  zone_breach: ShieldAlert,
  machine_stopped: Cog,
  queue_over: Users,
  shelf_gap: PackageOpen,
  price_mismatch: Tag,
  planogram_drift: LayoutGrid,
  model_drift: Activity,
  edge_offline: WifiOff,
  footfall_tick: Footprints,
  checkout_served: Receipt,
};

const NOISE: ReadonlySet<string> = new Set(["footfall_tick", "checkout_served"]);

export function EventStream({ limit = 40, minSeverity = 1, compact = false, kind }: { limit?: number; minSeverity?: number; compact?: boolean; kind?: EventKind }) {
  const t = useTranslations("dashboard");
  const site = useAppStore((s) => s.site);
  const live = useAppStore((s) => s.buffer.events);
  const q = useQuery({
    // Footfall and checkout ticks are the tape's trace, not stream items; ask the API for the operational kinds only.
    queryKey: ["events", site, "stream", limit, minSeverity, kind ?? "ops"],
    queryFn: async () => {
      if (kind) return api.events({ site, limit, kind });
      const lists = await Promise.all((["queue_over", "shelf_gap", "zone_breach", "ppe_violation", "machine_stopped"] as EventKind[]).map((k) => api.events({ site, limit, kind: k, min_severity: minSeverity })));
      return lists.flat();
    },
    enabled: !!site,
  });
  const keep = (e: ApiEvent) => !NOISE.has(e.kind) && e.severity >= minSeverity && (!kind || e.kind === kind);
  const merged = useMemo(() => {
    const map = new Map<string, ApiEvent>();
    for (const e of live) if (keep(e)) map.set(e.id, e);
    for (const e of q.data ?? []) if (keep(e)) map.set(e.id, e);
    return [...map.values()].sort((a, b) => (a.ts < b.ts ? 1 : -1)).slice(0, limit);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live, q.data, limit, minSeverity, kind]);

  if (q.isPending) {
    return (
      <ul className="flex flex-col gap-px p-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <li key={i} className="flex items-center gap-3 px-2 py-2.5">
            <Skeleton className="size-7 rounded-md" />
            <Skeleton className="h-3.5 w-1/2" />
            <Skeleton className="ms-auto h-3 w-12" />
          </li>
        ))}
      </ul>
    );
  }
  if (q.isError) return <ErrorState what={t("streamTitle").toLowerCase()} onRetry={() => q.refetch()} />;
  if (merged.length === 0) return <EmptyState title={t("empty")} hint={t("emptyStream")} icon={<Video className="size-6" strokeWidth={1.5} />} />;

  return (
    <ul className={cn("flex flex-col divide-y divide-hairline", compact ? "text-[0.8125rem]" : "text-sm")} aria-live="polite" aria-relevant="additions">
      <AnimatePresence initial={false}>
        {merged.map((e) => (
          <EventRow key={e.id} e={e} compact={compact} />
        ))}
      </AnimatePresence>
    </ul>
  );
}

function EventRow({ e, compact }: { e: ApiEvent; compact: boolean }) {
  const tk = useTranslations("kind");
  const td = useTranslations("dashboard");
  const tc = useTranslations("common");
  const locale = useLocale();
  const reduce = useReducedMotion();
  const Icon = ICONS[e.kind] ?? Footprints;
  const p = e.payload as Record<string, unknown>;
  const detail = [p.zone, p.count != null ? `${p.count} ${tc("people")}` : null, p.shelf_id ? `#${p.shelf_id}` : null, p.machine_id != null ? `M${p.machine_id}` : null]
    .filter(Boolean)
    .join(" · ");
  return (
    <motion.li
      layout={!reduce}
      initial={reduce ? false : { opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      className="group flex items-center gap-3 px-3 py-2.5 hover:bg-raised/60"
    >
      <span className={cn("grid size-7 shrink-0 place-items-center rounded-md border", e.severity === 3 ? "border-critical/30 bg-critical-soft text-critical" : e.severity === 2 ? "border-warn/30 bg-warn-soft text-warn" : "border-info/30 bg-info-soft text-info")}>
        <Icon className="size-3.5" strokeWidth={1.75} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate font-medium text-ink">{tk(e.kind)}</span>
          {!compact && <SevChip level={e.severity} />}
          {p.simulated === true && <span className="font-mono text-[0.625rem] uppercase tracking-wider text-ink-faint">{tc("simulated")}</span>}
        </div>
        <div className="truncate font-mono text-[0.6875rem] text-ink-muted">
          {e.camera} · {e.rule_id}
          {detail && ` · ${detail}`}
        </div>
      </div>
      <time dateTime={e.ts} className="num shrink-0 text-end text-[0.75rem] leading-tight text-ink-muted">
        {!isToday(e.ts) && <span className="block text-[0.625rem] text-ink-faint">{fmtDate(locale, e.ts)}</span>}
        {fmtTime(locale, e.ts, true)}
      </time>
      <Link href={`/events/${e.id}`} className="shrink-0 rounded-md border border-transparent px-2 py-1 text-[0.75rem] text-ink-muted opacity-70 transition group-hover:border-hairline-strong group-hover:text-ink group-hover:opacity-100 focus-visible:opacity-100">
        {td("openClip")}
      </Link>
    </motion.li>
  );
}
