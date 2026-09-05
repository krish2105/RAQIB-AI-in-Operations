"use client";

import { useQuery } from "@tanstack/react-query";
import { PackageOpen } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { fmtMinutes, fmtNumber, fmtPct } from "@/lib/format";
import { useAppStore } from "@/lib/store";
import { KpiTile } from "@/components/kpi/kpi-tile";
import { EventStream } from "@/components/stream/event-stream";
import { EmptyState, ErrorState, Panel, Skeleton } from "@/components/ui/panel";

export function ShelvesView() {
  const t = useTranslations("shelves");
  const locale = useLocale();
  const { site, profile } = useAppStore();
  const kpis = useQuery({ queryKey: ["kpis", site], queryFn: () => api.kpis(site), enabled: !!site });

  if (profile !== "retail") return <div className="panel"><EmptyState title={t("retailOnly")} icon={<PackageOpen className="size-6" strokeWidth={1.5} />} /></div>;
  const osa = kpis.data?.osa ?? {};
  const ttr = kpis.data?.time_to_restock_min ?? {};
  const shelves = Object.keys({ ...osa, ...ttr }).sort();

  return (
    <div className="flex flex-col gap-3">
      <h1 className="sr-only">{t("title")}</h1>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <KpiTile label={t("osa")} value={kpis.data?.osa_store ?? null} format={(n) => fmtPct(locale, n, 1)} loading={kpis.isPending} hero tone={(kpis.data?.osa_store ?? 1) >= 0.98 ? "ok" : "warn"} target={{ value: 0.98, met: (kpis.data?.osa_store ?? 0) >= 0.98 }} />
        <KpiTile label={t("gaps")} value={Object.values(osa).length} format={(n) => fmtNumber(locale, n)} loading={kpis.isPending} sub={t("sub")} />
        <KpiTile label={t("ttr")} value={Object.values(ttr).length ? Object.values(ttr).reduce((a, b) => a + b, 0) / Object.values(ttr).length : null} format={(n) => fmtMinutes(locale, n)} loading={kpis.isPending} />
      </div>

      <Panel eyebrow={t("title")} sub={t("sub")} bodyClassName="p-3">
        {kpis.isPending ? (
          <Skeleton className="h-40" />
        ) : kpis.isError ? (
          <ErrorState what={t("title").toLowerCase()} onRetry={() => kpis.refetch()} />
        ) : shelves.length === 0 ? (
          <EmptyState title={t("empty")} icon={<PackageOpen className="size-6" strokeWidth={1.5} />} />
        ) : (
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {shelves.map((s) => {
              const v = osa[s] ?? 1;
              return (
                <li key={s} className="panel-raised flex flex-col gap-2 p-4">
                  <div className="flex items-baseline justify-between">
                    <span className="display-wide text-lg font-semibold text-ink">{s}</span>
                    <span className={`num text-2xl ${v >= 0.98 ? "text-ok" : v >= 0.95 ? "text-warn" : "text-critical"}`}>{fmtPct(locale, v, 1)}</span>
                  </div>
                  <div className="h-1.5 w-full overflow-hidden rounded-full bg-sunken" role="meter" aria-valuemin={0} aria-valuemax={1} aria-valuenow={v} aria-label={`${s} ${t("osa")}`}>
                    <div className={`h-full rounded-full ${v >= 0.98 ? "bg-ok" : v >= 0.95 ? "bg-warn" : "bg-critical"}`} style={{ width: `${Math.round(v * 100)}%` }} />
                  </div>
                  <div className="flex justify-between font-mono text-[0.6875rem] text-ink-muted">
                    <span>{t("ttr")}</span>
                    <span className="text-ink">{fmtMinutes(locale, ttr[s])}</span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>

      <Panel eyebrow={t("recent")} bodyClassName="max-h-[480px] overflow-y-auto">
        <ShelfGapStream />
      </Panel>
    </div>
  );
}

function ShelfGapStream() {
  return <EventStream limit={30} minSeverity={1} compact kind="shelf_gap" />;
}
