"use client";

import { useLocale, useTranslations } from "next-intl";
import type { TwinWhatIf } from "@/lib/api";
import { fmtNumber, fmtPct } from "@/lib/format";
import { cn } from "@/lib/utils";

export function DeltaCard({ w }: { w: TwinWhatIf }) {
  const t = useTranslations("twin");
  const locale = useLocale();
  if (!w.sufficient || !w.before || !w.after || !w.delta) return <p className="p-3 text-sm text-ink-muted">{t("insufficient")}</p>;
  const rows: Array<{ k: string; b: string; a: string; d: number; good: (d: number) => boolean }> = [
    { k: t("staffHours"), b: fmtNumber(locale, w.before.staff_hours, 1), a: fmtNumber(locale, w.after.staff_hours, 1), d: w.delta.staff_hours, good: (d) => d <= 0 },
    { k: `${t("wait")} (${t("minutes")})`, b: fmtNumber(locale, w.before.customer_wait_min), a: fmtNumber(locale, w.after.customer_wait_min), d: w.delta.customer_wait_min, good: (d) => d <= 0 },
    { k: t("meanWq"), b: fmtNumber(locale, w.before.mean_wq_min, 2), a: fmtNumber(locale, w.after.mean_wq_min, 2), d: w.after.mean_wq_min - w.before.mean_wq_min, good: (d) => d <= 0 },
    { k: t("serviceLevel"), b: fmtPct(locale, w.before.service_level_model, 0), a: fmtPct(locale, w.after.service_level_model, 0), d: w.delta.service_level_model, good: (d) => d >= 0 },
    { k: t("peakRho"), b: fmtNumber(locale, w.before.peak_rho, 2), a: fmtNumber(locale, w.after.peak_rho, 2), d: w.delta.peak_rho, good: (d) => d <= 0 },
    { k: t("unstable"), b: String(w.before.unstable_slots), a: String(w.after.unstable_slots), d: w.after.unstable_slots - w.before.unstable_slots, good: (d) => d <= 0 },
  ];
  return (
    <div className="flex flex-col gap-2 p-3" data-testid="delta-card">
      <div className="flex items-baseline gap-3">
        <span className="display-wide text-3xl font-semibold text-ink num">{w.delta.wait_reduction_pct > 0 ? "−" : "+"}{fmtNumber(locale, Math.abs(w.delta.wait_reduction_pct), 1)}%</span>
        <span className="text-xs text-ink-muted">{t("wait")}</span>
        <span className={cn("ms-auto font-mono text-xs", w.delta.staff_hours > 0 ? "text-warn" : "text-ok")}>{w.delta.staff_hours > 0 ? "+" : ""}{fmtNumber(locale, w.delta.staff_hours, 2)} {t("staffHours").toLowerCase()}</span>
      </div>
      <table className="w-full font-mono text-[0.75rem]">
        <thead><tr className="text-ink-faint"><th className="text-start font-normal"> </th><th className="text-end font-normal">{t("before")}</th><th className="text-end font-normal">{t("after")}</th><th className="text-end font-normal">Δ</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.k} className="border-t border-hairline">
              <td className="py-1 text-ink-muted">{r.k}</td><td className="py-1 text-end text-ink">{r.b}</td><td className="py-1 text-end text-ink">{r.a}</td>
              <td className={cn("py-1 text-end", r.d === 0 ? "text-ink-faint" : r.good(r.d) ? "text-ok" : "text-warn")}>{r.d > 0 ? "+" : ""}{fmtNumber(locale, r.d, 2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {w.milp && <p className="text-[0.6875rem] text-ink-faint">{t("milp")}: {fmtNumber(locale, w.milp.staff_hours, 1)} {t("staffHours").toLowerCase()}, {fmtNumber(locale, w.milp.customer_wait_min)} {t("minutes")} {t("wait").toLowerCase()} · {t("muNote", { mu: fmtNumber(locale, w.mu_per_h ?? 0, 1), source: w.mu_source ?? "" })}</p>}
    </div>
  );
}
