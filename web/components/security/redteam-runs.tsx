"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { Chip, EmptyState, ErrorState, Panel, Skeleton } from "@/components/ui/panel";

function fmtEvidence(v: unknown): string {
  if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") return String(v);
  return JSON.stringify(v);
}

export function RedTeamRuns() {
  const t = useTranslations("security");
  const q = useQuery({ queryKey: ["security", "redteam"], queryFn: api.securityRedteam, staleTime: 60_000 });
  return (
    <Panel eyebrow={t("redteam")} sub={t("redteamSub")} className="h-full" bodyClassName="max-h-[520px] overflow-y-auto">
      {q.isPending ? <Skeleton className="m-3 h-40" /> : q.isError ? <ErrorState what={t("redteam").toLowerCase()} onRetry={() => q.refetch()} /> : q.data.runs.length === 0 ? (
        <EmptyState title={t("noResults")} hint={q.data.command} />
      ) : (
        <ul className="divide-y divide-hairline" data-testid="redteam-runs">
          {q.data.runs.map((r) => (
            <li key={r.asi} className="flex flex-col gap-1.5 px-3 py-2.5">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[0.6875rem] text-ink-faint">{r.asi}</span>
                <span className="min-w-0 flex-1 truncate text-[0.8125rem] text-ink">{r.test}</span>
                <Chip tone={r.passed ? "ok" : "critical"}>{r.passed ? t("pass") : t("fail")}</Chip>
                {r.seconds != null && <span className="font-mono text-[0.625rem] text-ink-faint">{t("seconds", { s: r.seconds })}</span>}
              </div>
              <dl className="flex flex-wrap gap-x-3 gap-y-0.5 font-mono text-[0.6875rem]">
                {Object.entries(r.evidence).map(([k, v]) => (
                  <div key={k} className="flex gap-1">
                    <dt className="text-ink-faint">{k}</dt>
                    <dd className="max-w-[28ch] truncate text-ink-muted" title={fmtEvidence(v)}>{fmtEvidence(v)}</dd>
                  </div>
                ))}
              </dl>
              {r.error && <p className="font-mono text-[0.6875rem] text-critical">{r.error}</p>}
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
