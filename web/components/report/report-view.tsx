"use client";

import { useQuery } from "@tanstack/react-query";
import { Printer } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { routing } from "@/i18n/routing";
import { api } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { ErrorState, Panel, Skeleton } from "@/components/ui/panel";
import { cn } from "@/lib/utils";

const LOCALE_LABEL: Record<string, string> = { en: "English", hi: "हिन्दी", ar: "العربية" };

export function ReportView() {
  const t = useTranslations("report");
  const uiLocale = useLocale();
  const site = useAppStore((s) => s.site);
  const [lang, setLang] = useState<string>(uiLocale);
  const rep = useQuery({ queryKey: ["report", site, lang], queryFn: () => api.report(site, lang), enabled: !!site, staleTime: 5 * 60_000 });

  return (
    <div className="flex flex-col gap-3">
      <h1 className="sr-only">{t("title")}</h1>
      <Panel
        eyebrow={t("title")}
        sub={t("sub")}
        className="print:border-0 print:shadow-none"
        actions={
          <div className="no-print flex items-center gap-2">
            <div role="tablist" aria-label={t("language")} className="flex gap-1 rounded-md border border-hairline p-0.5">
              {routing.locales.map((l) => (
                <button key={l} role="tab" aria-selected={lang === l} onClick={() => setLang(l)} className={cn("h-7 rounded px-2 text-[0.75rem]", lang === l ? "bg-raised text-ink" : "text-ink-muted hover:text-ink")}>
                  {LOCALE_LABEL[l]}
                </button>
              ))}
            </div>
            <Button variant="outline" onClick={() => window.print()}>
              <Printer className="size-4" strokeWidth={1.75} /> {t("print")}
            </Button>
          </div>
        }
        bodyClassName="p-5 sm:p-8"
      >
        {rep.isPending ? (
          <div className="flex flex-col gap-3">
            <Skeleton className="h-8 w-2/3" />
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="mt-4 h-40" />
            <Skeleton className="h-40" />
          </div>
        ) : rep.isError ? (
          <ErrorState what={t("title").toLowerCase()} onRetry={() => rep.refetch()} />
        ) : (
          <article className="report-md mx-auto max-w-[76ch]" dir={lang === "ar" ? "rtl" : "ltr"} lang={lang} data-testid="report">
            <Markdown remarkPlugins={[remarkGfm]}>{rep.data.markdown}</Markdown>
          </article>
        )}
      </Panel>
    </div>
  );
}
