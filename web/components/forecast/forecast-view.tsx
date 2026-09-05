"use client";

import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { Area, Bar, BarChart, CartesianGrid, ComposedChart, Line, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "@/lib/api";
import { fmtDate, fmtNumber, fmtPct, fmtTime } from "@/lib/format";
import { useAppStore } from "@/lib/store";
import { KpiTile } from "@/components/kpi/kpi-tile";
import { EmptyState, ErrorState, Panel, Skeleton } from "@/components/ui/panel";
import { cn } from "@/lib/utils";

const TARGETS = ["queue", "shelf", "machine"] as const;

export function ForecastView() {
  const t = useTranslations("forecast");
  const locale = useLocale();
  const { site, profile } = useAppStore();
  const [target, setTarget] = useState<(typeof TARGETS)[number]>(profile === "factory" ? "machine" : "queue");
  const fc = useQuery({ queryKey: ["forecast", site, target], queryFn: () => api.forecast(site, target, 24), enabled: !!site, staleTime: 5 * 60_000 });
  const wf = useQuery({ queryKey: ["workforce", site], queryFn: () => api.workforce(site), enabled: !!site && profile === "retail", staleTime: 5 * 60_000 });
  const d = fc.data;

  const series = d?.sufficient
    ? [
        ...d.history.slice(-72).map((h) => ({ ts: h.ts, label: fmtTime(locale, h.ts), history: h.value, forecast: null as number | null, baseline: null as number | null })),
        ...d.forecast.map((f) => ({ ts: f.ts, label: fmtTime(locale, f.ts), history: null as number | null, forecast: f.value, baseline: f.baseline })),
      ]
    : [];
  const splitLabel = d?.sufficient && d.forecast.length ? fmtTime(locale, d.forecast[0].ts) : undefined;

  return (
    <div className="flex flex-col gap-3">
      <h1 className="sr-only">{t("title")}</h1>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <KpiTile label={t("improvement")} value={d?.sufficient ? (d.improvement_pct ?? 0) / 100 : null} format={(n) => fmtPct(locale, n, 1)} loading={fc.isPending} hero tone={(d?.improvement_pct ?? 0) >= 20 ? "signal" : "warn"} target={{ value: 0.2, met: (d?.improvement_pct ?? 0) >= 20 }} sub={`${t("mae")} vs ${t("baseline").toLowerCase()}`} />
        <KpiTile label={t("mae")} value={d?.mae ?? null} format={(n) => fmtNumber(locale, n, 2)} loading={fc.isPending} />
        <KpiTile label={t("maeNaive")} value={d?.mae_naive ?? null} format={(n) => fmtNumber(locale, n, 2)} loading={fc.isPending} />
      </div>

      <Panel
        eyebrow={t("title")}
        sub={t("sub")}
        actions={
          <div role="tablist" className="flex gap-1 rounded-md border border-hairline p-0.5">
            {TARGETS.filter((x) => (profile === "retail" ? x !== "machine" : x === "machine" || x === "queue")).map((x) => (
              <button key={x} role="tab" aria-selected={target === x} onClick={() => setTarget(x)} className={cn("h-7 rounded px-2 font-mono text-[0.6875rem]", target === x ? "bg-raised text-ink" : "text-ink-muted hover:text-ink")}>
                {t(`target.${x}`)}
              </button>
            ))}
          </div>
        }
      >
        {fc.isPending ? (
          <Skeleton className="m-4 h-[300px]" />
        ) : fc.isError ? (
          <ErrorState what={t("title").toLowerCase()} onRetry={() => fc.refetch()} />
        ) : !d?.sufficient ? (
          <EmptyState title={t("insufficient", { reason: d?.reason ?? "" })} />
        ) : (
          <>
            <div className="h-[300px] w-full px-2 pt-3">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={series} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
                  <CartesianGrid stroke="var(--hairline)" vertical={false} />
                  <XAxis dataKey="label" tick={{ fill: "var(--ink-faint)", fontSize: 10, fontFamily: "var(--font-mono)" }} tickLine={false} axisLine={{ stroke: "var(--hairline-strong)" }} minTickGap={36} />
                  <YAxis tick={{ fill: "var(--ink-faint)", fontSize: 10, fontFamily: "var(--font-mono)" }} tickLine={false} axisLine={false} width={44} />
                  <Tooltip
                    contentStyle={{ background: "var(--surface)", border: "1px solid var(--hairline)", borderRadius: 8, fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--ink)" }}
                    labelFormatter={(_, payload) => { const p = payload?.[0]?.payload as { ts?: string } | undefined; return p?.ts ? `${fmtDate(locale, p.ts)} ${fmtTime(locale, p.ts)}` : ""; }}
                    formatter={(v: unknown, name: unknown) => [v == null ? "–" : fmtNumber(locale, Number(v), 1), name === "history" ? t("history") : name === "forecast" ? t("forecast") : t("baseline")]}
                  />
                  {splitLabel && <ReferenceLine x={splitLabel} stroke="var(--ink-muted)" strokeDasharray="3 3" label={{ value: "now", fill: "var(--ink-muted)", fontSize: 10, position: "insideTopRight" }} />}
                  <Area type="monotone" dataKey="history" stroke="var(--ink-muted)" fill="var(--ink-muted)" fillOpacity={0.12} strokeWidth={1.25} dot={false} isAnimationActive={false} connectNulls={false} />
                  <Line type="monotone" dataKey="baseline" stroke="var(--info)" strokeDasharray="4 3" strokeWidth={1.25} dot={false} isAnimationActive={false} />
                  <Line type="monotone" dataKey="forecast" stroke="var(--signal)" strokeWidth={2} dot={false} isAnimationActive={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <div className="flex flex-wrap items-center gap-4 px-4 pb-3 font-mono text-[0.6875rem] text-ink-muted">
              <span className="inline-flex items-center gap-1.5"><span aria-hidden className="inline-block h-0.5 w-4 bg-ink-muted" />{t("history")}</span>
              <span className="inline-flex items-center gap-1.5"><span aria-hidden className="inline-block h-0.5 w-4 bg-signal" />{t("forecast")}</span>
              <span className="inline-flex items-center gap-1.5"><span aria-hidden className="inline-block h-0.5 w-4 border-t border-dashed border-info" />{t("baseline")}</span>
              {d.peaks.length > 0 && (
                <span className="ms-auto">
                  {t("peaks")}: {d.peaks.slice(0, 3).map((p) => fmtTime(locale, p.ts)).join(", ")}
                </span>
              )}
            </div>
          </>
        )}
      </Panel>

      {profile === "retail" && (
        <Panel eyebrow={t("workforceTitle")} sub={t("workforceSub")}>
          {wf.isPending ? (
            <Skeleton className="m-4 h-[220px]" />
          ) : wf.isError ? (
            <ErrorState what={t("workforceTitle").toLowerCase()} onRetry={() => wf.refetch()} />
          ) : !wf.data?.sufficient ? (
            <EmptyState title={wf.data?.reason ?? t("insufficient", { reason: "" })} />
          ) : (
            <div className="grid grid-cols-1 gap-3 p-3 lg:grid-cols-12">
              <div className="h-[220px] lg:col-span-9">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={wf.data.slots!.map((s, i) => ({ slot: fmtTime(locale, s), tills: wf.data!.tills![i], rho: wf.data!.rho![i], lam: wf.data!.lam![i] }))} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
                    <CartesianGrid stroke="var(--hairline)" vertical={false} />
                    <XAxis dataKey="slot" tick={{ fill: "var(--ink-faint)", fontSize: 10, fontFamily: "var(--font-mono)" }} tickLine={false} axisLine={{ stroke: "var(--hairline-strong)" }} minTickGap={30} />
                    <YAxis allowDecimals={false} tick={{ fill: "var(--ink-faint)", fontSize: 10, fontFamily: "var(--font-mono)" }} tickLine={false} axisLine={false} />
                    <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--hairline)", borderRadius: 8, fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--ink)" }} formatter={(v: unknown, name: unknown) => [v == null ? "–" : fmtNumber(locale, Number(v), name === "tills" ? 0 : 2), name === "tills" ? t("tills") : name === "rho" ? "ρ" : "λ/h"]} />
                    <ReferenceLine y={wf.data.observed_tills} stroke="var(--ink-muted)" strokeDasharray="3 3" />
                    <Bar dataKey="tills" fill="var(--signal)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
              <dl className="grid grid-cols-2 gap-3 self-center font-mono text-[0.75rem] lg:col-span-3 lg:grid-cols-1">
                <Stat k={t("staffHours")} v={fmtNumber(locale, wf.data.staff_hours!, 1)} tone="text-signal" />
                <Stat k={t("baselineHours")} v={fmtNumber(locale, wf.data.baseline_staff_hours!, 1)} />
                <Stat k={t("savings")} v={`${fmtNumber(locale, wf.data.savings_hours!, 1)} h`} tone="text-ok" />
                <Stat k="μ" v={`${fmtNumber(locale, wf.data.mu!, 0)}/h`} />
              </dl>
            </div>
          )}
        </Panel>
      )}
    </div>
  );
}

function Stat({ k, v, tone = "text-ink" }: { k: string; v: string; tone?: string }) {
  return (
    <div className="panel-raised flex flex-col gap-1 p-3">
      <dt className="eyebrow">{k}</dt>
      <dd className={cn("num text-xl", tone)}>{v}</dd>
    </div>
  );
}
