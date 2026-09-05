"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { api, type ApiAction } from "@/lib/api";
import { fmtNumber } from "@/lib/format";
import { useAppStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Panel, Skeleton } from "@/components/ui/panel";
import { cn } from "@/lib/utils";
import { ProposalCard } from "./proposal-card";

const FILTERS: Array<ApiAction["status"] | "all"> = ["proposed", "executed", "rejected", "failed", "all"];

export function ActionsView() {
  const t = useTranslations("actions");
  const locale = useLocale();
  const site = useAppStore((s) => s.site);
  const qc = useQueryClient();
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("proposed");
  const actions = useQuery({ queryKey: ["actions", site, filter], queryFn: () => api.actions({ site, status: filter === "all" ? undefined : filter, limit: 200 }), enabled: !!site, refetchInterval: 20_000 });
  const audit = useQuery({ queryKey: ["toolcalls", site, "summary"], queryFn: () => api.toolcallSummary(site), enabled: !!site });
  const seed = useMutation({
    mutationFn: () => api.seed(site, 21),
    onSuccess: () => {
      qc.invalidateQueries();
    },
  });

  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-12">
      <div className="lg:col-span-8">
        <Panel
          eyebrow={t("title")}
          sub={t("sub")}
          bodyClassName="flex flex-col gap-2 p-3"
          actions={
            <div role="tablist" aria-label={t("title")} className="flex gap-1 rounded-md border border-hairline p-0.5">
              {FILTERS.map((f) => (
                <button key={f} role="tab" aria-selected={filter === f} onClick={() => setFilter(f)} className={cn("h-7 rounded px-2 font-mono text-[0.6875rem] capitalize", filter === f ? "bg-raised text-ink" : "text-ink-muted hover:text-ink")}>
                  {t(f)}
                </button>
              ))}
            </div>
          }
        >
          <h1 className="sr-only">{t("title")}</h1>
          {actions.isPending ? (
            Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-32" />)
          ) : actions.isError ? (
            <ErrorState what={t("title").toLowerCase()} onRetry={() => actions.refetch()} />
          ) : actions.data.length === 0 ? (
            <EmptyState title={t("proposed") === t(filter) ? t("proposed") : t(filter)} hint={t("seedNote")} />
          ) : (
            actions.data.map((a) => <ProposalCard key={a.id} action={a} />)
          )}
        </Panel>
      </div>

      <div className="flex flex-col gap-3 lg:col-span-4">
        <Panel eyebrow={t("auditTitle")} sub={audit.data ? t("auditSub", { calls: fmtNumber(locale, audit.data.total_calls), cost: `$${fmtNumber(locale, audit.data.total_cost_usd, 4)}` }) : undefined} bodyClassName="p-3">
          {audit.isPending ? (
            <Skeleton className="h-32" />
          ) : audit.isError ? (
            <ErrorState what={t("auditTitle").toLowerCase()} onRetry={() => audit.refetch()} />
          ) : (
            <table className="w-full font-mono text-[0.75rem]">
              <thead className="text-ink-faint">
                <tr className="text-start">
                  <th className="pb-1 text-start font-normal">tool</th>
                  <th className="pb-1 text-end font-normal">calls</th>
                  <th className="pb-1 text-end font-normal">ok</th>
                  <th className="pb-1 text-end font-normal">ms</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(audit.data.by_tool).map(([tool, s]) => (
                  <tr key={tool} className="border-t border-hairline text-ink-muted">
                    <td className="py-1.5 text-ink">{tool}</td>
                    <td className="py-1.5 text-end">{fmtNumber(locale, s.calls)}</td>
                    <td className={cn("py-1.5 text-end", s.ok < s.calls && "text-warn")}>{fmtNumber(locale, s.ok)}</td>
                    <td className="py-1.5 text-end">{fmtNumber(locale, s.latency_ms_avg)}</td>
                  </tr>
                ))}
                {Object.keys(audit.data.by_tool).length === 0 && (
                  <tr>
                    <td colSpan={4} className="py-4 text-center text-ink-faint">–</td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </Panel>

        <Panel eyebrow="Demo data" bodyClassName="flex flex-col gap-2 p-4">
          <p className="text-xs leading-relaxed text-ink-muted">{t("seedNote")}</p>
          <Button variant="outline" onClick={() => seed.mutate()} busy={seed.isPending} disabled={seed.isPending} data-testid="seed">
            <Database className="size-4" strokeWidth={1.75} /> {seed.isPending ? t("seeding") : t("seed")}
          </Button>
          {seed.isSuccess && <p className="font-mono text-[0.6875rem] text-ok">{t("seeded", { n: fmtNumber(locale, seed.data.inserted) })}</p>}
          {seed.isError && <p className="font-mono text-[0.6875rem] text-critical">{String(seed.error)}</p>}
        </Panel>
      </div>
    </div>
  );
}
