"use client";

import { useQuery } from "@tanstack/react-query";
import { ShieldCheck, ShieldX } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { Chip, EmptyState, ErrorState, Panel, Skeleton } from "@/components/ui/panel";
import { cn } from "@/lib/utils";

export function AsiScorecard() {
  const t = useTranslations("security");
  const locale = useLocale();
  const q = useQuery({ queryKey: ["security", "scorecard"], queryFn: api.securityScorecard, staleTime: 60_000 });
  const allPass = q.data ? q.data.total > 0 && q.data.failed === 0 : false;
  return (
    <Panel
      eyebrow={t("scorecard")}
      sub={t("scorecardSub")}
      actions={q.data && q.data.total > 0 ? (
        <span className="flex items-center gap-2">
          <Chip tone={allPass ? "ok" : "critical"} data-testid="asi-summary">{t("passed", { passed: q.data.passed, total: q.data.total })}</Chip>
          {q.data.date && <span className="font-mono text-[0.6875rem] text-ink-faint">{t("lastRun")} {fmtDate(locale, q.data.date)}</span>}
        </span>
      ) : null}
    >
      {q.isPending ? <Skeleton className="m-3 h-40" /> : q.isError ? <ErrorState what={t("scorecard").toLowerCase()} onRetry={() => q.refetch()} /> : q.data.total === 0 ? (
        <EmptyState title={t("noResults")} hint={t("noResultsHint")} />
      ) : (
        <ol className="grid grid-cols-1 gap-px bg-hairline sm:grid-cols-2 xl:grid-cols-5" data-testid="asi-scorecard">
          {q.data.results.map((r) => (
            <li key={r.asi} className={cn("flex flex-col gap-1.5 bg-surface p-3", !r.passed && "bg-critical-soft/40")} data-testid={`asi-${r.asi}`} data-passed={r.passed}>
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-[0.6875rem] uppercase tracking-wider text-ink-faint">{r.asi}</span>
                {r.passed ? <ShieldCheck className="size-4 text-ok" strokeWidth={1.75} aria-label={t("pass")} /> : <ShieldX className="size-4 text-critical" strokeWidth={1.75} aria-label={t("fail")} />}
              </div>
              <span className="text-[0.9375rem] font-medium text-ink">{r.risk}</span>
              <p className="text-xs leading-snug text-ink-muted"><span className="text-ink-faint">{t("control")}: </span>{r.control}</p>
              <p className="text-xs leading-snug text-ink-muted"><span className="text-ink-faint">{t("attack")}: </span>{r.test}</p>
              {r.error && <p className="font-mono text-[0.6875rem] text-critical">{r.error}</p>}
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}
