"use client";

import { useTranslations } from "next-intl";

export interface WhatIfInputs {
  staff_delta: number;
  express_lane: boolean;
}

export function WhatIfPanel({ value, onChange, disabled }: { value: WhatIfInputs; onChange: (v: WhatIfInputs) => void; disabled?: boolean }) {
  const t = useTranslations("twin");
  return (
    <div className="flex flex-col gap-3 p-3" data-testid="what-if">
      <label className="flex flex-col gap-1 text-xs text-ink-muted">
        <span className="flex justify-between"><span>{t("staffDelta")}</span><span className="font-mono text-ink">{value.staff_delta > 0 ? "+" : ""}{value.staff_delta}</span></span>
        <input type="range" min={-2} max={3} step={1} value={value.staff_delta} disabled={disabled} onChange={(e) => onChange({ ...value, staff_delta: Number(e.target.value) })} className="accent-[var(--signal)]" data-testid="staff-delta" aria-label={t("staffDelta")} />
      </label>
      <label className="flex items-center gap-2 text-xs text-ink-muted">
        <input type="checkbox" checked={value.express_lane} disabled={disabled} onChange={(e) => onChange({ ...value, express_lane: e.target.checked })} className="accent-[var(--signal)]" data-testid="express-lane" />
        {t("express")}
      </label>
      <p className="text-[0.6875rem] text-ink-faint">{t("whatIfSub")}</p>
    </div>
  );
}
