"use client";

import { useQuery } from "@tanstack/react-query";
import { Cog } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { api, type ApiKpis } from "@/lib/api";
import { fmtNumber } from "@/lib/format";
import { useAppStore } from "@/lib/store";
import { EmptyState, Skeleton } from "@/components/ui/panel";
import { cn } from "@/lib/utils";

/** Factory profile: machines from the site config with stopped/running state and downtime. */
export function MachineCard({ kpis }: { kpis: ApiKpis | undefined }) {
  const t = useTranslations("kpi");
  const tk = useTranslations("kind");
  const locale = useLocale();
  const site = useAppStore((s) => s.site);
  const siteQ = useQuery({ queryKey: ["site", site], queryFn: () => api.site(site), enabled: !!site, staleTime: 5 * 60_000 });
  if (siteQ.isPending) return <Skeleton className="m-4 h-40" />;
  const machines = siteQ.data?.machines ?? [];
  if (!machines.length) return <EmptyState title="–" icon={<Cog className="size-6" strokeWidth={1.5} />} />;
  const stopped = new Set(kpis?.stopped_machines ?? []);
  return (
    <ul className="divide-y divide-hairline">
      {machines.map((m) => {
        const id = String(m.machine_id);
        const isStopped = stopped.has(id);
        return (
          <li key={id} className="flex items-center gap-3 px-4 py-3">
            <span className={cn("grid size-8 place-items-center rounded-md border", isStopped ? "border-warn/30 bg-warn-soft text-warn" : "border-hairline bg-raised text-ink-muted")}>
              <Cog className={cn("size-4", !isStopped && "motion-safe:animate-[spin_6s_linear_infinite]")} strokeWidth={1.75} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[0.75rem] text-ink-muted">{String(m.code ?? id)}</span>
                <span className="truncate text-sm text-ink">{String(m.name ?? "")}</span>
              </div>
              <div className="font-mono text-[0.6875rem] text-ink-faint">{String(m.scheduled ?? "")}</div>
            </div>
            <div className="text-end">
              <div className={cn("font-mono text-[0.6875rem] uppercase tracking-wider", isStopped ? "text-warn" : "text-ok")}>{isStopped ? tk("machine_stopped") : "running"}</div>
              <div className="num text-sm text-ink">{fmtNumber(locale, kpis?.downtime_min ?? 0)} {t("downtimeSub").split(",")[1]?.trim() ?? "min"}</div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
