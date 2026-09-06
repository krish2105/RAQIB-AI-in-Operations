"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, FileText } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useRef } from "react";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api";
import { Chip, ErrorState, Panel, Skeleton } from "@/components/ui/panel";
import { cn } from "@/lib/utils";

/** Document viewer: every chunk in order; the cited chunk (?chunk=) is highlighted and scrolled into view. */
export function DocumentView({ id, chunk }: { id: string; chunk?: string }) {
  const t = useTranslations("ask");
  const doc = useQuery({ queryKey: ["document", id], queryFn: () => api.document(id) });
  const target = useRef<HTMLElement>(null);
  useEffect(() => {
    target.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [doc.data, chunk]);

  if (doc.isPending) return <Skeleton className="h-[60dvh]" />;
  if (doc.isError || !doc.data) return <div className="panel"><ErrorState what={t("document").toLowerCase()} onRetry={() => doc.refetch()} /></div>;
  const d = doc.data;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Link href="/ask" className="inline-flex items-center gap-1.5 text-xs text-ink-muted hover:text-ink">
          <ArrowLeft className="size-3.5 rtl:rotate-180" /> {t("back")}
        </Link>
        <h1 className="display-wide text-xl font-semibold text-ink">{d.title}</h1>
        <Chip tone="neutral">{d.kind}</Chip>
        <span className="font-mono text-[0.6875rem] text-ink-faint">{d.chunks.length} × {t("chunk").toLowerCase()}</span>
      </div>
      <Panel eyebrow={t("document")} bodyClassName="divide-y divide-hairline">
        {d.chunks.map((c) => {
          const hit = c.id === chunk;
          return (
            <section key={c.id} ref={hit ? target : undefined} className={cn("px-4 py-3", hit && "bg-signal-soft")} data-testid={hit ? "cited-chunk" : undefined}>
              <div className="mb-1 flex items-center gap-2 text-[0.6875rem] text-ink-muted">
                <FileText className="size-3.5" aria-hidden />
                <span className="truncate">{String(c.meta.heading ?? "")}</span>
                {hit && <Chip tone="signal">{t("citedSpan")}</Chip>}
              </div>
              <p className="whitespace-pre-wrap text-[0.875rem] leading-relaxed text-ink" dir="auto">{c.text.split("\n").slice(1).join("\n") || c.text}</p>
            </section>
          );
        })}
      </Panel>
    </div>
  );
}
