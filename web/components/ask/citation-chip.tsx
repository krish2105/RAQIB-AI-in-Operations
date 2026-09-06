"use client";

import { FileText, Video, Activity, BarChart3 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import type { AskCitation } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

/** One chip per citation. Events link to the event page; documents to the viewer at the cited section. */
export function CitationChip({ c, index, compact = false }: { c: AskCitation; index: number; compact?: boolean }) {
  const t = useTranslations("ask");
  const tk = useTranslations("kind");
  const locale = useLocale();
  const isEvent = c.kind === "event" && !!c.event_id;
  const isDoc = c.kind === "document" && !!c.doc_id;
  const href = isEvent ? `/events/${c.event_id}` : isDoc ? `/documents/${c.doc_id}?chunk=${encodeURIComponent(c.chunk_id)}` : null;
  const Icon = isEvent ? (c.clip_url ? Video : Activity) : isDoc ? FileText : BarChart3;
  const label = isEvent && c.event_kind && tk.has(c.event_kind) ? tk(c.event_kind as Parameters<typeof tk>[0]) : isDoc ? c.doc_title ?? t("document") : c.span;
  const sev = c.severity ?? 0;
  const body = (
    <>
      <span className="font-mono text-[0.625rem] text-ink-faint">{index + 1}</span>
      <Icon className="size-3.5 shrink-0" strokeWidth={1.75} aria-hidden />
      <span className="truncate">{label}</span>
      {!compact && <span className="ms-1 font-mono text-[0.625rem] text-ink-faint">{isDoc ? c.span : fmtDateTime(locale, c.ts)}</span>}
    </>
  );
  const cls = cn(
    "inline-flex h-7 max-w-full items-center gap-1.5 rounded-full border px-2 text-[0.75rem] transition-colors",
    sev >= 3 ? "border-critical/40 text-critical hover:bg-critical-soft" : sev === 2 ? "border-warn/40 text-warn hover:bg-warn-soft" : "border-hairline-strong text-ink hover:bg-raised",
  );
  if (!href) return <span className={cls} data-testid="citation">{body}</span>;
  return (
    <Link href={href} className={cls} data-testid="citation" data-chunk={c.chunk_id} title={isEvent ? t("openEvent") : t("openDocument")}>
      {body}
    </Link>
  );
}
