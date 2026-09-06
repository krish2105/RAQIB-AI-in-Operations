"use client";

import { useLocale, useTranslations } from "next-intl";
import type { CrewAgent } from "@/lib/api";
import { fmtRelative } from "@/lib/format";
import { useNow } from "@/lib/use-now";
import { Chip } from "@/components/ui/panel";
import { BudgetBar } from "./budget-bar";
import { cn } from "@/lib/utils";

export const STATUS_TONE: Record<string, "neutral" | "signal" | "ok" | "warn" | "critical"> = {
  ok: "ok", running: "signal", flagged: "warn", budget_exceeded: "critical", killed: "critical", error: "critical",
};

export function AgentCard({ a }: { a: CrewAgent }) {
  const t = useTranslations("crew");
  const locale = useLocale();
  const now = useNow(5000);
  const lit = !!a.last_run && now - new Date(a.last_run.started).getTime() < 60_000;
  return (
    <article className={cn("panel-raised flex flex-col gap-2 p-3", lit && "border-signal/50")} data-testid={`agent-${a.name}`} data-lit={lit || undefined}>
      <header className="flex flex-wrap items-center gap-2">
        <h3 className="text-[0.9375rem] font-medium text-ink">{a.name}</h3>
        {a.mandatory && <Chip tone="signal">{t("mandatory")}</Chip>}
        {a.last_run && <Chip tone={STATUS_TONE[a.last_run.status] ?? "neutral"}>{t.has(`status.${a.last_run.status}`) ? t(`status.${a.last_run.status}` as Parameters<typeof t>[0]) : a.last_run.status}</Chip>}
        <span className="ms-auto font-mono text-[0.6875rem] text-ink-faint">{a.runs} {t("runs")}{a.flagged ? ` · ${a.flagged} ${t("flagged")}` : ""}</span>
      </header>
      <p className="text-xs text-ink-muted">{a.role}</p>
      <div className="flex flex-wrap gap-1">
        {a.allowed_tools.length ? a.allowed_tools.map((x) => <Chip key={x} tone="neutral">{x}</Chip>) : <Chip tone="neutral">{t("noTools")}</Chip>}
      </div>
      <div className="font-mono text-[0.6875rem] text-ink-faint">{t("triggers")}: {a.triggers.join(", ")}</div>
      <BudgetBar label={t("calls")} used={a.last_run?.tool_calls ?? 0} max={a.budget.max_tool_calls} unit="" />
      <BudgetBar label="USD" used={a.last_run?.cost_usd ?? 0} max={a.budget.max_usd} unit="$" />
      <BudgetBar label={t("seconds")} used={Math.round(a.last_run?.seconds ?? 0)} max={a.budget.max_seconds} unit="s" />
      <div className="font-mono text-[0.6875rem] text-ink-faint">{t("lastRun")}: {a.last_run ? fmtRelative(locale, a.last_run.started, now) : t("never")}</div>
    </article>
  );
}
