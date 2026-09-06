"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { EmptyState, ErrorState, Panel, Skeleton } from "@/components/ui/panel";
import { cn } from "@/lib/utils";
import { DriftChart } from "./drift-chart";
import { EdgeHealth } from "./edge-health";
import { KPI_KEYS, Leaderboard } from "./leaderboard";

export function FleetView() {
  const t = useTranslations("fleet");
  const site = useAppStore((s) => s.site);
  const [kpi, setKpi] = useState<(typeof KPI_KEYS)[number]>("service_level");
  const [window, setWindow] = useState(24);
  const board = useQuery({ queryKey: ["fleet", "board", kpi, window], queryFn: () => api.fleetLeaderboard(kpi, window), refetchInterval: 60_000 });
  const drift = useQuery({ queryKey: ["fleet", "drift", site], queryFn: () => api.fleetDrift(site), enabled: !!site, refetchInterval: 60_000 });
  const health = useQuery({ queryKey: ["fleet", "health", site], queryFn: () => api.fleetHealth(site), enabled: !!site, refetchInterval: 30_000 });
  return (
    <div className="flex flex-col gap-3">
      <h1 className="sr-only">{t("title")}</h1>
      <Panel eyebrow={t("leaderboard")} sub={t("leaderboardSub")} actions={
        <div className="flex items-center gap-2">
          <select value={kpi} onChange={(e) => setKpi(e.target.value as (typeof KPI_KEYS)[number])} aria-label={t("kpi")} className="h-8 rounded-md border border-hairline-strong bg-surface px-2 font-mono text-[0.75rem] text-ink" data-testid="kpi-select">
            {KPI_KEYS.map((k) => <option key={k} value={k}>{t(`kpis.${k}`)}</option>)}
          </select>
          <div role="tablist" aria-label={t("window")} className="flex gap-1 rounded-md border border-hairline p-0.5">
            {[24, 24 * 7].map((w) => <button key={w} role="tab" aria-selected={window === w} onClick={() => setWindow(w)} className={cn("h-7 rounded px-2 font-mono text-[0.6875rem]", window === w ? "bg-raised text-ink" : "text-ink-muted hover:text-ink")}>{w === 24 ? "24h" : "7d"}</button>)}
          </div>
        </div>
      }>
        {board.isPending ? <Skeleton className="h-24 m-3" /> : board.isError ? <ErrorState what={t("leaderboard").toLowerCase()} onRetry={() => board.refetch()} /> : <Leaderboard stores={board.data.stores} kpi={kpi} />}
      </Panel>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Panel eyebrow={t("drift")} sub={t("driftSub")} bodyClassName="divide-y divide-hairline">
          {drift.isPending ? <Skeleton className="h-40 m-3" /> : drift.isError ? <ErrorState what={t("drift").toLowerCase()} onRetry={() => drift.refetch()} /> : !drift.data.cameras.length ? <EmptyState title={t("noDrift")} /> : drift.data.cameras.map((c) => <DriftChart key={c.camera} cam={c} />)}
        </Panel>
        <Panel eyebrow={t("health")} sub={t("healthSub")} bodyClassName="flex flex-col gap-3 p-3">
          {health.isPending ? <Skeleton className="h-40" /> : health.isError ? <ErrorState what={t("health").toLowerCase()} onRetry={() => health.refetch()} /> : !health.data.boxes.length ? <EmptyState title={t("noBoxes")} /> : health.data.boxes.map((b) => <EdgeHealth key={b.box_id} box={b} />)}
        </Panel>
      </div>
    </div>
  );
}
