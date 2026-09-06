"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion, useReducedMotion } from "motion/react";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { api, type ApiAction } from "@/lib/api";
import { fmtDateTime, fmtPct } from "@/lib/format";
import { isProposal } from "@/lib/severity";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/panel";
import { cn } from "@/lib/utils";

const STATUS_TONE: Record<ApiAction["status"], "neutral" | "signal" | "ok" | "warn" | "critical"> = {
  proposed: "signal",
  approved: "ok",
  executed: "ok",
  rejected: "neutral",
  failed: "critical",
};

export function ProposalCard({ action, compact = false }: { action: ApiAction; compact?: boolean }) {
  const t = useTranslations("actions");
  const locale = useLocale();
  const qc = useQueryClient();
  const reduce = useReducedMotion();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["actions", action.site] });
    qc.invalidateQueries({ queryKey: ["toolcalls", action.site] });
  };
  const approve = useMutation({ mutationFn: () => api.approve(action.id, "operator"), onSuccess: invalidate });
  const reject = useMutation({ mutationFn: () => api.reject(action.id, "operator"), onSuccess: invalidate });
  const busy = approve.isPending || reject.isPending;
  const toolLabel = t.has(`tool.${action.tool}`) ? t(`tool.${action.tool}` as Parameters<typeof t>[0]) : action.tool;
  const proposal = isProposal(action.tool);

  return (
    <motion.article
      layout={!reduce}
      className={cn("panel-raised flex flex-col gap-3 p-4", action.status === "proposed" && "border-signal/30")}
      data-testid={`action-${action.id}`}
    >
      <header className="flex flex-wrap items-center gap-2">
        <h3 className="text-[0.9375rem] font-medium text-ink">{toolLabel}</h3>
        <Chip tone={STATUS_TONE[action.status]}>{t(action.status)}</Chip>
        <Chip tone="neutral">{proposal ? t("proposal") : t("autonomous")}</Chip>
        {action.agent && <Chip tone="signal" data-testid="agent-chip">{action.agent}</Chip>}
        <span className="ms-auto font-mono text-[0.6875rem] text-ink-faint">
          {fmtDateTime(locale, action.created_at)} · {t("confidence")} {fmtPct(locale, action.confidence, 0)}
        </span>
      </header>

      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 font-mono text-[0.75rem]">
        {Object.entries(action.args).map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-ink-faint">{k}</dt>
            <dd className="truncate text-ink">{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd>
          </div>
        ))}
      </dl>

      {!compact && (
        <p className="text-[0.8125rem] leading-relaxed text-ink-muted">
          <span className="eyebrow me-2">{t("reasoning")}</span>
          {action.reasoning}
        </p>
      )}

      {action.result && !compact && (
        <details className="text-[0.75rem]">
          <summary className="cursor-pointer text-ink-muted hover:text-ink">{t("result")}</summary>
          <pre className="mt-2 max-h-40 overflow-auto rounded-md bg-sunken p-2 font-mono text-[0.6875rem] text-ink-muted">{JSON.stringify(action.result, null, 2)}</pre>
        </details>
      )}

      <footer className="flex flex-wrap items-center gap-2">
        {action.event_id && (
          <Link href={`/events/${action.event_id}`} className="font-mono text-[0.6875rem] text-ink-muted underline-offset-4 hover:text-ink hover:underline">
            {t("event")} {action.event_id.slice(-6)}
          </Link>
        )}
        {action.decided_by && action.decided_by !== "agent" && <span className="font-mono text-[0.6875rem] text-ink-faint">{t("decidedBy", { who: action.decided_by })}</span>}
        {action.status === "proposed" && (
          <div className="ms-auto flex gap-2">
            <Button variant="danger" onClick={() => reject.mutate()} disabled={busy} busy={reject.isPending} data-testid="reject">
              {reject.isPending ? t("rejecting") : t("reject")}
            </Button>
            <Button variant="primary" onClick={() => approve.mutate()} disabled={busy} busy={approve.isPending} data-testid="approve">
              {approve.isPending ? t("approving") : t("approve")}
            </Button>
          </div>
        )}
      </footer>
    </motion.article>
  );
}
