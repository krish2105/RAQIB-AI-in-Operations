"use client";

import { useLocale, useTranslations } from "next-intl";
import type { FleetStore } from "@/lib/api";
import { fmtNumber, fmtPct } from "@/lib/format";
import { Chip } from "@/components/ui/panel";

export const KPI_KEYS = ["service_level", "osa", "compliance", "agent_cost_usd", "events", "actions"] as const;

export function fmtKpi(locale: string, kpi: string, v: number | null): string {
  if (v === null || v === undefined) return "–";
  if (kpi === "service_level" || kpi === "osa" || kpi === "compliance") return fmtPct(locale, v, 1);
  if (kpi === "agent_cost_usd") return `$${fmtNumber(locale, v, 4)}`;
  return fmtNumber(locale, v);
}

export function Leaderboard({ stores, kpi }: { stores: FleetStore[]; kpi: string }) {
  const t = useTranslations("fleet");
  const locale = useLocale();
  return (
    <table className="w-full font-mono text-[0.75rem]" data-testid="leaderboard">
      <thead><tr className="text-ink-faint"><th className="px-3 text-start font-normal">#</th><th className="text-start font-normal">{t("store")}</th><th className="text-start font-normal">{t("region")}</th><th className="text-end font-normal">{t(`kpis.${kpi}` as Parameters<typeof t>[0])}</th><th className="text-end font-normal">{t("kpis.events")}</th><th className="px-3 text-end font-normal">{t("edge")}</th></tr></thead>
      <tbody>
        {stores.map((s) => (
          <tr key={s.id} className="border-t border-hairline" data-testid={`store-${s.id}`}>
            <td className="px-3 py-1.5 text-ink-faint">{s.rank}</td>
            <td className="py-1.5 text-ink">{s.name}</td>
            <td className="py-1.5 text-ink-muted">{s.region}</td>
            <td className="py-1.5 text-end text-ink num">{fmtKpi(locale, kpi, s[kpi as keyof FleetStore] as number | null)}</td>
            <td className="py-1.5 text-end text-ink-muted">{fmtNumber(locale, s.events)}</td>
            <td className="px-3 py-1.5 text-end"><Chip tone={s.edge.offline ? "critical" : s.edge.online ? "ok" : "neutral"}>{s.edge.online}/{s.edge.boxes}</Chip></td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
