"use client";

import { useLocale, useTranslations } from "next-intl";
import type { EdgeBox } from "@/lib/api";
import { fmtNumber, fmtRelative } from "@/lib/format";
import { useNow } from "@/lib/use-now";
import { Chip } from "@/components/ui/panel";

const TONE: Record<EdgeBox["status"], "ok" | "warn" | "critical" | "neutral"> = { online: "ok", degraded: "warn", offline: "critical", unknown: "neutral" };

export function EdgeHealth({ box }: { box: EdgeBox }) {
  const t = useTranslations("fleet");
  const locale = useLocale();
  const now = useNow(5000);
  return (
    <article className="panel-raised flex flex-col gap-2 p-3" data-testid={`box-${box.box_id}`} data-status={box.status}>
      <header className="flex flex-wrap items-center gap-2">
        <h3 className="font-mono text-[0.9375rem] text-ink">{box.box_id}</h3>
        <Chip tone={TONE[box.status]}>{t(`status.${box.status}` as Parameters<typeof t>[0])}</Chip>
        <span className="ms-auto font-mono text-[0.6875rem] text-ink-faint">{t("lastSeen")} {box.last_seen ? fmtRelative(locale, box.last_seen, now) : "–"}</span>
      </header>
      <dl className="grid grid-cols-2 gap-x-3 gap-y-0.5 font-mono text-[0.75rem] sm:grid-cols-4">
        <dt className="text-ink-faint">{t("fps")}</dt><dd className="text-ink">{box.fps !== null ? fmtNumber(locale, box.fps, 1) : "–"}</dd>
        <dt className="text-ink-faint">{t("queue")}</dt><dd className="text-ink">{box.queue_depth ?? "–"}</dd>
        <dt className="text-ink-faint">°C</dt><dd className="text-ink">{box.temp_c !== null ? fmtNumber(locale, box.temp_c, 0) : "–"}</dd>
        <dt className="text-ink-faint">{t("model")}</dt><dd className="text-ink">{box.detector} {box.model_hash ?? ""}</dd>
      </dl>
      <div className="flex h-8 items-end gap-px" aria-hidden>
        {box.fps_24h.slice(-48).map((p, i) => <span key={i} className="flex-1 rounded-t bg-signal/60" style={{ height: `${Math.min(100, (p.fps / 30) * 100)}%` }} />)}
      </div>
    </article>
  );
}
