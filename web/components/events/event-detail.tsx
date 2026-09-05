"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Camera, Clock, Crosshair, Gauge, MapPin, ScrollText, Video, VideoOff } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api";
import { fmtDateTime, fmtPct } from "@/lib/format";
import { ProposalCard } from "@/components/actions/proposal-card";
import { EmptyState, ErrorState, Panel, SevChip, Skeleton } from "@/components/ui/panel";

const RULE_TEXT: Record<string, string> = {
  R01: "Person inside a work area with no helmet box over the head region for ≥ 2 s.",
  R02: "Person foot point inside an exclusion zone. Immediate.",
  R03: "Machine ROI classified stopped for ≥ 120 s during the scheduled run.",
  R10: "≥ N persons inside a queue zone for ≥ 60 s (N from site thresholds).",
  R11: "Shelf ROI empty-ratio above 0.4 for ≥ 5 min.",
  R12: "Person track entered the entrance zone for the first time.",
  R13: "Person track left a checkout zone after dwelling ≥ 20 s (service completion, μ estimator).",
};

export function EventDetail({ id }: { id: string }) {
  const t = useTranslations("event");
  const tk = useTranslations("kind");
  const ts = useTranslations("severity");
  const locale = useLocale();
  const ev = useQuery({ queryKey: ["event", id], queryFn: () => api.event(id), refetchInterval: (q) => (q.state.data && !q.state.data.has_clip && q.state.data.severity >= 2 ? 10_000 : false) });
  const acts = useQuery({ queryKey: ["actions", ev.data?.site, "event", id], queryFn: () => api.actionsForEvent(ev.data!.site, id), enabled: !!ev.data });

  if (ev.isPending) return <Skeleton className="h-[60dvh]" />;
  if (ev.isError || !ev.data) return <div className="panel"><ErrorState what={t("title").toLowerCase()} onRetry={() => ev.refetch()} /></div>;
  const e = ev.data;
  const p = e.payload as Record<string, unknown>;
  const conf = typeof p.confidence === "number" ? p.confidence : null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/" className="inline-flex items-center gap-1.5 text-xs text-ink-muted hover:text-ink">
          <ArrowLeft className="size-3.5 rtl:rotate-180" /> {t("back")}
        </Link>
        <h1 className="display-wide text-xl font-semibold text-ink">{tk(e.kind)}</h1>
        <SevChip level={e.severity} label={`${ts(String(e.severity) as "1" | "2" | "3")}`} />
        <span className="font-mono text-[0.6875rem] text-ink-faint">{e.id}</span>
        {p.simulated === true && <span className="rounded-full border border-hairline px-2 py-0.5 font-mono text-[0.6875rem] text-ink-muted">{t("simulatedNote")}</span>}
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-12">
        <Panel eyebrow={t("clip")} className="lg:col-span-7" bodyClassName="relative aspect-video bg-sunken">
          {e.has_clip ? (
            <video controls playsInline preload="metadata" className="absolute inset-0 h-full w-full" src={api.clipUrl(e.id)} data-testid="clip" />
          ) : (
            <EmptyState
              icon={e.severity >= 2 ? <Video className="size-6" strokeWidth={1.5} /> : <VideoOff className="size-6" strokeWidth={1.5} />}
              title={e.severity >= 2 ? t("clipPending") : t("noClip")}
            />
          )}
          {e.has_clip && (
            <div className="pointer-events-none absolute inset-x-0 top-0 flex items-center gap-2 bg-gradient-to-b from-black/50 to-transparent px-3 py-2 font-mono text-[0.6875rem] text-white/90">
              <Crosshair className="size-3.5" /> {e.camera} · {e.rule_id}
            </div>
          )}
        </Panel>

        <Panel eyebrow={t("detection")} className="lg:col-span-5" bodyClassName="p-4">
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2.5 text-sm">
            <Row icon={Clock} k={t("time")} v={fmtDateTime(locale, e.ts)} />
            <Row icon={Camera} k={t("camera")} v={e.camera} />
            <Row icon={MapPin} k={t("zone")} v={String(p.zone ?? "–")} />
            <Row icon={Gauge} k={t("confidence")} v={conf === null ? "–" : fmtPct(locale, conf, 0)} bar={conf} />
            <Row icon={ScrollText} k={t("rule")} v={`${e.rule_id} — ${RULE_TEXT[e.rule_id] ?? ""}`} />
          </dl>
          <div className="mt-4">
            <div className="eyebrow mb-1.5">{t("payload")}</div>
            <pre className="max-h-48 overflow-auto rounded-md bg-sunken p-3 font-mono text-[0.6875rem] leading-relaxed text-ink-muted">{JSON.stringify(p, null, 2)}</pre>
          </div>
        </Panel>

        <Panel eyebrow={t("decision")} className="lg:col-span-12" bodyClassName="flex flex-col gap-2 p-3">
          {acts.isPending ? <Skeleton className="h-24" /> : acts.isError ? <ErrorState what={t("decision").toLowerCase()} onRetry={() => acts.refetch()} /> : acts.data.length === 0 ? <EmptyState title={t("noDecision")} /> : acts.data.map((a) => <ProposalCard key={a.id} action={a} />)}
        </Panel>
      </div>
    </div>
  );
}

function Row({ icon: Icon, k, v, bar }: { icon: React.ComponentType<{ className?: string; strokeWidth?: number }>; k: string; v: string; bar?: number | null }) {
  return (
    <>
      <dt className="flex items-center gap-1.5 text-ink-muted">
        <Icon className="size-3.5" strokeWidth={1.75} /> {k}
      </dt>
      <dd className="min-w-0 text-ink">
        <span className="font-mono text-[0.8125rem]">{v}</span>
        {typeof bar === "number" && (
          <div className="mt-1 h-1 w-full rounded-full bg-raised" role="meter" aria-valuemin={0} aria-valuemax={1} aria-valuenow={bar}>
            <div className={`h-full rounded-full ${bar < 0.6 ? "bg-warn" : "bg-signal"}`} style={{ width: `${Math.round(bar * 100)}%` }} />
          </div>
        )}
      </dd>
    </>
  );
}
