"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { api, type ApiOpinion } from "@/lib/api";
import { fmtDateTime, fmtPct } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Chip, EmptyState, Skeleton } from "@/components/ui/panel";

export function verdictOf(o: ApiOpinion): "agrees" | "disagrees" | "unavailable" {
  if (o.status !== "ok" || o.agrees === null) return "unavailable";
  return o.agrees ? "agrees" : "disagrees";
}

export function OpinionRow({ o, withEvent = false }: { o: ApiOpinion; withEvent?: boolean }) {
  const t = useTranslations("watch");
  const locale = useLocale();
  const v = verdictOf(o);
  const tone = v === "agrees" ? "ok" : v === "disagrees" ? "warn" : "neutral";
  return (
    <li className="flex flex-col gap-1.5 px-3 py-2.5" data-testid="opinion" data-verdict={v}>
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone={tone}>{t(v)}</Chip>
        {v !== "unavailable" && <span className="font-mono text-[0.6875rem] text-ink-muted">{t("confidence")} {fmtPct(locale, o.confidence, 0)}</span>}
        <Chip tone="neutral">{t(`rule`, { n: o.rule_severity })}</Chip>
        {o.suggested_severity !== null && <Chip tone={o.disagreement ? "warn" : "neutral"}>{t("suggested", { n: o.suggested_severity })}</Chip>}
        {o.review_action_id !== null && <Chip tone="signal">{t("reviewRequested")}</Chip>}
        <span className="ms-auto font-mono text-[0.625rem] text-ink-faint">
          {t(`trigger.${o.trigger}` as Parameters<typeof t>[0])} · {t(`status.${o.status}` as Parameters<typeof t>[0])} · {fmtDateTime(locale, o.ts)}
        </span>
      </div>
      {o.observed && o.observed !== "unavailable" && (
        <p className="text-[0.8125rem] leading-snug text-ink"><span className="text-ink-muted">{t("observed")}: </span>{o.observed}</p>
      )}
      {o.disagreement_reason && <p className="text-[0.8125rem] leading-snug text-warn"><span className="text-ink-muted">{t("reason")}: </span>{o.disagreement_reason}</p>}
      {withEvent && <Link href={`/events/${o.event_id}`} className="font-mono text-[0.6875rem] text-ink-faint hover:text-ink">{o.event_id}</Link>}
    </li>
  );
}

/** Opinions for one event with an on-demand button (event page) or for a whole site (Watch tab). */
export function OpinionPanel({ site, eventId }: { site: string; eventId?: string }) {
  const t = useTranslations("watch");
  const qc = useQueryClient();
  const ops = useQuery({ queryKey: ["opinions", site, eventId ?? "all"], queryFn: () => api.opinions(site, eventId), enabled: !!site });
  const ask = useMutation({ mutationFn: () => api.requestOpinion(eventId!), onSuccess: () => qc.invalidateQueries({ queryKey: ["opinions", site] }) });
  return (
    <div className="flex flex-col">
      {eventId && (
        <div className="flex items-center justify-between gap-2 border-b border-hairline px-3 py-2 text-xs text-ink-muted">
          <span>{t("opinionsSub")}</span>
          <Button variant="outline" onClick={() => ask.mutate()} busy={ask.isPending} disabled={ask.isPending} data-testid="request-opinion">
            {ask.isPending ? t("requesting") : t("requestOpinion")}
          </Button>
        </div>
      )}
      {ops.isPending ? (
        <Skeleton className="h-20 m-3" />
      ) : !ops.data?.length ? (
        <EmptyState title={t("opinionsEmpty")} />
      ) : (
        <ul className="divide-y divide-hairline">
          {ops.data.map((o) => (
            <OpinionRow key={o.id} o={o} withEvent={!eventId} />
          ))}
        </ul>
      )}
    </div>
  );
}
