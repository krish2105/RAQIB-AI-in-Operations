"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Upload } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useRef } from "react";
import { api } from "@/lib/api";
import { fmtNumber } from "@/lib/format";
import { useAppStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { Chip, ErrorState, Skeleton } from "@/components/ui/panel";

export function IntegrationsPanel() {
  const t = useTranslations("settings");
  const locale = useLocale();
  const site = useAppStore((s) => s.site);
  const qc = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const summary = useQuery({ queryKey: ["pos-summary", site], queryFn: () => api.posSummary(site), enabled: !!site });
  const upload = useMutation({
    mutationFn: (f: File) => api.posImport(site, f, f.name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pos-summary", site] });
      qc.invalidateQueries({ queryKey: ["kpis", site] });
    },
  });
  return (
    <div className="flex flex-col gap-4 p-3" data-testid="integrations">
      <section className="flex flex-col gap-2">
        <h3 className="text-[0.9375rem] font-medium text-ink">{t("pos")}</h3>
        <p className="text-xs text-ink-muted">{t("posSub")}</p>
        <div className="flex flex-wrap items-center gap-2">
          <input ref={input} type="file" accept=".csv,text/csv" className="hidden" data-testid="pos-file" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }} />
          <Button variant="primary" onClick={() => input.current?.click()} busy={upload.isPending} disabled={upload.isPending} data-testid="pos-upload">
            <Upload className="size-3.5" /> {upload.isPending ? t("uploading") : t("upload")}
          </Button>
          <a href={api.posSampleUrl(site)} className="inline-flex h-9 items-center gap-2 rounded-md border border-hairline-strong px-3 text-[0.8125rem] text-ink hover:bg-raised" download>
            <Download className="size-3.5" /> {t("sample")}
          </a>
          {upload.isSuccess && <Chip tone="ok" data-testid="pos-result">{t("imported", { inserted: upload.data.inserted, duplicates: upload.data.duplicates, invalid: upload.data.invalid })}</Chip>}
          {upload.isError && <Chip tone="critical">{(upload.error as Error).message}</Chip>}
        </div>
        {summary.isPending ? <Skeleton className="h-16" /> : summary.isError ? <ErrorState what={t("pos").toLowerCase()} onRetry={() => summary.refetch()} /> : (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 font-mono text-[0.75rem] sm:grid-cols-4" data-testid="pos-summary">
            <dt className="text-ink-faint">{t("transactions")}</dt><dd className="text-ink">{fmtNumber(locale, summary.data.transactions)}</dd>
            <dt className="text-ink-faint">{t("muPos")}</dt><dd className="text-ink">{summary.data.mu_pos_per_h !== null ? `${fmtNumber(locale, summary.data.mu_pos_per_h, 1)} ${t("perTill")}` : t("none")}</dd>
            <dt className="text-ink-faint">{t("muVideo")}</dt><dd className="text-ink">{summary.data.mu_video_per_h !== null ? `${fmtNumber(locale, summary.data.mu_video_per_h, 1)} ${t("perTill")}` : t("none")}</dd>
            <dt className="text-ink-faint">{t("muSource")}</dt><dd className="text-ink"><Chip tone={summary.data.mu_source === "pos" ? "signal" : "neutral"}>{summary.data.mu_source === "pos" ? t("sourcePos") : t("sourceVideo")}</Chip></dd>
          </dl>
        )}
        {summary.data && (
          <div className="flex flex-wrap items-center gap-2 text-[0.6875rem] text-ink-faint">
            <span>{t("adapters")}:</span>
            {Object.entries(summary.data.adapters).map(([k, v]) => <Chip key={k} tone={v === "ready" ? "ok" : "neutral"}>{k} · {v.startsWith("stub") ? t("status.stub") : t("status.ready")}</Chip>)}
          </div>
        )}
      </section>
    </div>
  );
}
