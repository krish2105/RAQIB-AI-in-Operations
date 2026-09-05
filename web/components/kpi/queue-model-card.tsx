"use client";

import { useLocale, useTranslations } from "next-intl";
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { QueueSlot } from "@/lib/api";
import { fmtNumber, fmtTime } from "@/lib/format";
import { EmptyState } from "@/components/ui/panel";

export function QueueModelChart({ slots }: { slots: QueueSlot[] }) {
  const t = useTranslations("dashboard");
  const locale = useLocale();
  const data = slots.slice(-24).map((s) => ({
    slot: fmtTime(locale, s.slot_start),
    model: s.wq_model_min == null ? null : +s.wq_model_min.toFixed(2),
    observed: s.wq_observed_min == null ? null : +s.wq_observed_min.toFixed(2),
    rho: +s.rho.toFixed(2),
    lam: s.lam_per_h,
  }));
  if (!data.length) return <EmptyState title={t("empty")} />;
  const hasObserved = data.some((d) => d.observed != null);
  return (
    <div className="flex h-full flex-col">
      <div className="h-[220px] w-full px-2 pt-3">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
            <CartesianGrid stroke="var(--hairline)" vertical={false} />
            <XAxis dataKey="slot" tick={{ fill: "var(--ink-faint)", fontSize: 10, fontFamily: "var(--font-mono)" }} tickLine={false} axisLine={{ stroke: "var(--hairline-strong)" }} interval="preserveStartEnd" minTickGap={28} />
            <YAxis yAxisId="wq" tick={{ fill: "var(--ink-faint)", fontSize: 10, fontFamily: "var(--font-mono)" }} tickLine={false} axisLine={false} width={44} />
            <YAxis yAxisId="rho" orientation="right" domain={[0, 1.2]} hide />
            <Tooltip
              cursor={{ stroke: "var(--hairline-strong)" }}
              contentStyle={{ background: "var(--surface)", border: "1px solid var(--hairline)", borderRadius: 8, fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--ink)" }}
              labelStyle={{ color: "var(--ink-muted)" }}
              formatter={(v: unknown, name: unknown) => [v == null ? "–" : fmtNumber(locale, Number(v), 2), name === "model" ? t("wqModel") : name === "observed" ? t("wqObserved") : t("rho")]}
            />
            <Bar yAxisId="rho" dataKey="rho" fill="var(--signal)" opacity={0.18} radius={[2, 2, 0, 0]} isAnimationActive={false} />
            <Line yAxisId="wq" type="monotone" dataKey="model" stroke="var(--signal)" strokeWidth={1.75} dot={false} connectNulls isAnimationActive={false} />
            {hasObserved && <Line yAxisId="wq" type="monotone" dataKey="observed" stroke="var(--warn)" strokeWidth={1.5} strokeDasharray="4 3" dot={{ r: 2.5, fill: "var(--warn)", strokeWidth: 0 }} connectNulls={false} isAnimationActive={false} />}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="flex flex-wrap items-center gap-4 px-4 pb-3 font-mono text-[0.6875rem] text-ink-muted">
        <span className="inline-flex items-center gap-1.5"><span aria-hidden className="inline-block h-0.5 w-4 bg-signal" />{t("wqModel")} (min)</span>
        <span className="inline-flex items-center gap-1.5"><span aria-hidden className="inline-block h-0.5 w-4 border-t border-dashed border-warn" />{t("wqObserved")} (min)</span>
        <span className="inline-flex items-center gap-1.5"><span aria-hidden className="inline-block h-2.5 w-3 rounded-sm bg-signal/25" />{t("rho")}</span>
        <span className="ms-auto text-ink-faint">{t("muNote")}</span>
      </div>
    </div>
  );
}
