"use client";

import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import type { ShelfRow } from "@/lib/api";
import { fmtPct } from "@/lib/format";
import { Chip } from "@/components/ui/panel";

export function PlanogramDiff({ shelf }: { shelf: ShelfRow }) {
  const t = useTranslations("shelves");
  const locale = useLocale();
  const p = shelf.planogram;
  if (p.compliance === null) return <p className="px-3 py-2 text-xs text-ink-muted">{t("noPlanogram")}</p>;
  return (
    <div className="flex flex-col gap-2 px-3 py-2" data-testid={`planogram-${shelf.shelf_id}`}>
      <div className="flex flex-wrap items-center gap-2 font-mono text-[0.75rem]">
        <span className={`num text-xl ${p.compliance >= 0.9 ? "text-ok" : p.compliance >= 0.7 ? "text-warn" : "text-critical"}`}>{fmtPct(locale, p.compliance, 0)}</span>
        <span className="text-ink-faint">{t("compliance")} · {p.present}/{p.expected} {t("present")}</span>
        {p.event_id && <Link href={`/events/${p.event_id}`} className="ms-auto text-[0.6875rem] text-ink-faint hover:text-ink">R15 · {p.events}</Link>}
      </div>
      <div className="flex flex-wrap gap-1">
        {p.missing.map((s) => <Chip key={`m${s}`} tone="critical">{t("missing")} · {s}</Chip>)}
        {p.misplaced.map((s) => <Chip key={`x${s}`} tone="warn">{t("misplaced")} · {s}</Chip>)}
      </div>
    </div>
  );
}
