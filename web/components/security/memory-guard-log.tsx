"use client";

import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { fmtTime } from "@/lib/format";
import { useAppStore } from "@/lib/store";
import { Chip, EmptyState, ErrorState, Panel, Skeleton } from "@/components/ui/panel";

export function MemoryGuardLog() {
  const t = useTranslations("security");
  const locale = useLocale();
  const site = useAppStore((s) => s.site);
  const guard = useQuery({ queryKey: ["security", "guard", site], queryFn: () => api.securityMemoryGuard(site), enabled: !!site, refetchInterval: 60_000 });
  const audit = useQuery({ queryKey: ["security", "audit", site], queryFn: () => api.securityAudit(site), enabled: !!site, refetchInterval: 60_000 });
  return (
    <Panel eyebrow={t("guard")} sub={t("guardSub")}>
      <div className="grid grid-cols-1 gap-px bg-hairline lg:grid-cols-3" data-testid="memory-guard">
        <section className="flex flex-col gap-2 bg-surface p-3">
          <h3 className="text-[0.8125rem] font-medium text-ink">{t("quarantined")}</h3>
          {guard.isPending ? <Skeleton className="h-20" /> : guard.isError ? <ErrorState what={t("guard").toLowerCase()} onRetry={() => guard.refetch()} /> : guard.data.quarantined.length === 0 ? <EmptyState title={t("noQuarantine")} /> : (
            <ul className="flex flex-col divide-y divide-hairline">
              {guard.data.quarantined.map((m) => (
                <li key={m.id} className="flex flex-col gap-0.5 py-2 text-xs">
                  <div className="flex items-center gap-2"><Chip tone="warn">{m.agent}</Chip><span className="font-mono text-ink">{m.key}</span><span className="ms-auto font-mono text-[0.625rem] text-ink-faint">{fmtTime(locale, m.ts, true)}</span></div>
                  <span className="truncate font-mono text-[0.6875rem] text-ink-muted" title={m.preview}>{m.preview}</span>
                  {m.reason && <span className="text-[0.6875rem] text-ink-faint">{t("reason")}: {m.reason}</span>}
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="flex flex-col gap-2 bg-surface p-3">
          <h3 className="text-[0.8125rem] font-medium text-ink">{t("audit")}</h3>
          {audit.isPending ? <Skeleton className="h-20" /> : audit.isError ? <ErrorState what={t("audit").toLowerCase()} onRetry={() => audit.refetch()} /> : audit.data.flagged.length === 0 ? <EmptyState title={t("noFlags")} /> : (
            <ul className="flex flex-col divide-y divide-hairline">
              {audit.data.flagged.map((r) => (
                <li key={r.id} className="flex items-center gap-2 py-2 text-xs">
                  <Chip tone="critical">{String(r.flag?.finding ?? "flagged")}</Chip>
                  <span className="font-mono text-ink">{r.agent}</span>
                  <span className="truncate text-ink-muted">{String(r.flag?.note ?? r.trigger)}</span>
                  <span className="ms-auto font-mono text-[0.625rem] text-ink-faint">{fmtTime(locale, r.started, true)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="flex flex-col gap-2 bg-surface p-3">
          <h3 className="text-[0.8125rem] font-medium text-ink">{t("snapshots")}</h3>
          {guard.isPending ? <Skeleton className="h-20" /> : guard.isError ? null : guard.data.snapshots.length === 0 ? <EmptyState title={t("noSnapshots")} /> : (
            <ul className="flex flex-col divide-y divide-hairline font-mono text-[0.6875rem]">
              {guard.data.snapshots.map((s) => (
                <li key={s.id} className="flex items-center gap-2 py-1.5"><span className="text-ink">#{s.id}</span><span className="text-ink-muted">{t("entries", { n: s.count })}</span><span className="text-ink-faint">{s.taken_by}</span><span className="ms-auto text-ink-faint">{fmtTime(locale, s.ts, true)}</span></li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </Panel>
  );
}
