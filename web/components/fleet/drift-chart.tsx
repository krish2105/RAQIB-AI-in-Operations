"use client";

import { useLocale, useTranslations } from "next-intl";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { CameraDrift } from "@/lib/api";
import { fmtTime } from "@/lib/format";
import { Chip } from "@/components/ui/panel";

export function DriftChart({ cam }: { cam: CameraDrift }) {
  const t = useTranslations("fleet");
  const locale = useLocale();
  const data = cam.hourly.map((h) => ({ hour: fmtTime(locale, h.hour), psi: h.psi }));
  const over = cam.hours_over >= 3;
  return (
    <div className="flex flex-col gap-2 p-3" data-testid={`drift-${cam.camera}`}>
      <div className="flex flex-wrap items-center gap-2 font-mono text-[0.75rem]">
        <span className="text-ink">{cam.camera}</span>
        <Chip tone={over ? "critical" : cam.psi > cam.threshold ? "warn" : "ok"}>{t("psi")} {cam.psi.toFixed(2)}</Chip>
        <span className="text-ink-faint">{cam.hours_over} {t("hoursOver")} · {cam.baseline_n} {t("baseline")}</span>
        {cam.suggestion && <span className="basis-full text-[0.75rem] text-warn">{t(`suggestion.${cam.suggestion}` as Parameters<typeof t>[0])}</span>}
      </div>
      <div className="h-36 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: -20 }}>
            <CartesianGrid stroke="var(--hairline)" vertical={false} />
            <XAxis dataKey="hour" tick={{ fontSize: 10, fill: "var(--ink-faint)" }} interval={5} />
            <YAxis domain={[0, Math.max(0.5, cam.psi + 0.1)]} tick={{ fontSize: 10, fill: "var(--ink-faint)" }} />
            <Tooltip contentStyle={{ background: "var(--surface)", border: "1px solid var(--hairline-strong)", fontSize: 11 }} />
            <ReferenceLine y={cam.threshold} stroke="var(--warn)" strokeDasharray="4 4" />
            <Line type="monotone" dataKey="psi" stroke="var(--signal)" dot={false} strokeWidth={1.5} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
