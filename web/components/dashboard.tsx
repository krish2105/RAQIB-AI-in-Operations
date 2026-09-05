"use client";

import { useQuery } from "@tanstack/react-query";
import { motion, useReducedMotion, type Variants } from "motion/react";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api";
import { fmtNumber, fmtPct } from "@/lib/format";
import { useAppStore } from "@/lib/store";
import { KpiTile } from "@/components/kpi/kpi-tile";
import { MachineCard } from "@/components/kpi/machine-card";
import { QueueModelChart } from "@/components/kpi/queue-model-card";
import { EventStream } from "@/components/stream/event-stream";
import { ProposalCard } from "@/components/actions/proposal-card";
import { FloorPanel } from "@/components/floor/floor-panel";
import { EmptyState, ErrorState, Panel, Skeleton } from "@/components/ui/panel";

const grid: Variants = { hidden: {}, show: { transition: { staggerChildren: 0.06, delayChildren: 0.05 } } };
const cell: Variants = { hidden: { opacity: 0, y: 14 }, show: { opacity: 1, y: 0, transition: { duration: 0.55, ease: [0.16, 1, 0.3, 1] } } };

export function Dashboard() {
  const t = useTranslations("dashboard");
  const tk = useTranslations("kpi");
  const locale = useLocale();
  const reduce = useReducedMotion();
  const site = useAppStore((s) => s.site);
  const profile = useAppStore((s) => s.profile);
  const kpis = useQuery({ queryKey: ["kpis", site], queryFn: () => api.kpis(site), enabled: !!site, refetchInterval: 30_000 });
  const proposals = useQuery({ queryKey: ["actions", site, "proposed"], queryFn: () => api.actions({ site, status: "proposed", limit: 6 }), enabled: !!site, refetchInterval: 20_000 });
  const k = kpis.data;
  const pct = (n: number) => fmtPct(locale, n, 1);
  const num = (d = 0) => (n: number) => fmtNumber(locale, n, d);

  const tiles =
    profile === "retail"
      ? [
          { label: tk("serviceLevel"), value: k?.service_level ?? null, format: pct, sub: tk("serviceLevelSub"), hero: true, tone: (k?.service_level ?? 1) >= 0.9 ? "signal" : "warn", target: { value: 0.9, met: (k?.service_level ?? 0) >= 0.9 } },
          { label: tk("osa"), value: k?.osa_store ?? null, format: pct, sub: tk("osaSub"), tone: (k?.osa_store ?? 1) >= 0.98 ? "ok" : "neutral", target: { value: 0.98, met: (k?.osa_store ?? 0) >= 0.98 } },
          { label: tk("avgQueue"), value: k?.avg_queue ?? null, format: num(1), sub: tk("avgQueueSub"), tone: (k?.avg_queue ?? 0) > 5 ? "warn" : "neutral" },
          { label: tk("footfall"), value: k?.footfall_per_hour ?? null, format: num(0), sub: tk("footfallSub", { total: fmtNumber(locale, k?.footfall ?? 0) }) },
        ]
      : [
          { label: tk("compliance"), value: k?.compliance ?? null, format: pct, sub: tk("complianceSub"), hero: true, tone: (k?.compliance ?? 1) >= 0.95 ? "signal" : "critical", target: { value: 0.95, met: (k?.compliance ?? 0) >= 0.95 } },
          { label: tk("downtime"), value: k?.downtime_min ?? null, format: num(0), sub: tk("downtimeSub"), tone: (k?.downtime_min ?? 0) > 30 ? "warn" : "neutral" },
          { label: tk("breaches"), value: k?.breaches ?? null, format: num(0), sub: tk("breachesSub"), tone: (k?.breaches ?? 0) > 0 ? "critical" : "ok" },
          { label: tk("footfall"), value: k?.footfall_per_hour ?? null, format: num(0), sub: tk("footfallSub", { total: fmtNumber(locale, k?.footfall ?? 0) }) },
        ];

  return (
    <motion.div variants={reduce ? undefined : grid} initial={reduce ? false : "hidden"} animate="show" className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-12 lg:auto-rows-[minmax(0,auto)]">
      <h1 className="sr-only">{t("title")}</h1>
      {tiles.map((tile, i) => (
        <motion.div key={tile.label} variants={cell} className={tile.hero ? "sm:col-span-2 lg:col-span-4" : i === 1 ? "lg:col-span-3" : i === 2 ? "lg:col-span-2" : "lg:col-span-3"}>
          {kpis.isError ? (
            <div className="panel h-full">
              <ErrorState what={tile.label.toLowerCase()} onRetry={() => kpis.refetch()} />
            </div>
          ) : (
            <KpiTile {...tile} tone={tile.tone as never} loading={kpis.isPending} />
          )}
        </motion.div>
      ))}

      <motion.div variants={cell} className="sm:col-span-2 lg:col-span-8 lg:row-span-2">
        <Panel eyebrow={t("floorTitle")} sub={t("floorSub")} className="h-full min-h-[380px]" bodyClassName="relative">
          <FloorPanel height={420} />
        </Panel>
      </motion.div>

      <motion.div variants={cell} className="sm:col-span-2 lg:col-span-4 lg:row-span-2">
        <Panel eyebrow={t("streamTitle")} className="h-full min-h-[380px]" bodyClassName="max-h-[560px] overflow-y-auto">
          <EventStream limit={40} compact />
        </Panel>
      </motion.div>

      <motion.div variants={cell} className="sm:col-span-2 lg:col-span-7">
        {profile === "retail" ? (
          <Panel eyebrow={t("queueModelTitle")} sub={t("queueModelSub")} className="h-full">
            {kpis.isPending ? <Skeleton className="m-4 h-[220px]" /> : kpis.isError ? <ErrorState what={t("queueModelTitle").toLowerCase()} onRetry={() => kpis.refetch()} /> : <QueueModelChart slots={k?.queue_model ?? []} />}
          </Panel>
        ) : (
          <Panel eyebrow={tk("stopped")} sub={tk("stoppedSub")} className="h-full">
            <MachineCard kpis={k} />
          </Panel>
        )}
      </motion.div>

      <motion.div variants={cell} className="sm:col-span-2 lg:col-span-5">
        <Panel
          eyebrow={t("proposalsTitle")}
          sub={t("proposalsSub")}
          className="h-full"
          bodyClassName="flex flex-col gap-2 p-3"
          actions={
            <Link href="/actions" className="text-xs text-ink-muted underline-offset-4 hover:text-ink hover:underline">
              {t("viewAll")}
            </Link>
          }
        >
          {proposals.isPending ? (
            <Skeleton className="h-28" />
          ) : proposals.isError ? (
            <ErrorState what={t("proposalsTitle").toLowerCase()} onRetry={() => proposals.refetch()} />
          ) : proposals.data.length === 0 ? (
            <EmptyState title={t("empty")} hint={t("emptyProposals")} />
          ) : (
            proposals.data.slice(0, 3).map((a) => <ProposalCard key={a.id} action={a} compact />)
          )}
        </Panel>
      </motion.div>
    </motion.div>
  );
}
