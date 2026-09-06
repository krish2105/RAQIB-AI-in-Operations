"use client";

import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useEffect } from "react";
import { api } from "@/lib/api";
import { fmtNumber, fmtPct } from "@/lib/format";
import { useAppStore } from "@/lib/store";
import { KpiTile } from "@/components/kpi/kpi-tile";
import { ErrorState, Panel, Skeleton } from "@/components/ui/panel";
import { CameraTile } from "./camera-tile";
import { CaptionTicker } from "./caption-ticker";
import { OpinionPanel } from "./opinion-panel";

export function WatchView() {
  const t = useTranslations("watch");
  const locale = useLocale();
  const { site, detections, pushDetections } = useAppStore();
  const siteQ = useQuery({ queryKey: ["site", site], queryFn: () => api.site(site), enabled: !!site, staleTime: 5 * 60_000 });
  const latest = useQuery({ queryKey: ["detections-latest", site], queryFn: () => api.detectionsLatest(site), enabled: !!site });
  const summary = useQuery({ queryKey: ["opinion-summary", site], queryFn: () => api.opinionSummary(site), enabled: !!site, refetchInterval: 30_000 });
  const streamOn = useQuery({ queryKey: ["stream-on"], queryFn: async () => (await api.cameraStatus().catch(() => ({ configured: false }))).configured, staleTime: 60_000 });
  useEffect(() => {
    latest.data?.forEach(pushDetections);
  }, [latest.data, pushDetections]);

  const cams = siteQ.data?.cameras ?? [];
  return (
    <div className="flex flex-col gap-3">
      <h1 className="sr-only">{t("title")}</h1>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <KpiTile label={t("opinionsCount")} value={summary.data?.opinions ?? null} format={(n) => fmtNumber(locale, n)} loading={summary.isPending} sub={t("opinionsSub")} />
        <KpiTile label={t("available")} value={summary.data?.available ?? null} format={(n) => fmtNumber(locale, n)} loading={summary.isPending} />
        <KpiTile label={t("disagreementRate")} value={summary.data?.disagreement_rate ?? null} format={(n) => fmtPct(locale, n, 0)} loading={summary.isPending} tone={(summary.data?.disagreement_rate ?? 0) > 0.2 ? "warn" : "ok"} />
      </div>
      <Panel eyebrow={t("title")} sub={streamOn.data ? t("sub") : `${t("streamOff")} ${t("streamHint")}`} bodyClassName="p-3">
        {siteQ.isPending ? (
          <Skeleton className="h-64" />
        ) : siteQ.isError ? (
          <ErrorState what={t("title").toLowerCase()} onRetry={() => siteQ.refetch()} />
        ) : (
          <div className={cams.length > 1 ? "grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3" : "grid grid-cols-1 gap-3"}>
            {cams.slice(0, 6).map((c) => (
              <CameraTile key={c.name} site={site} camera={c} zones={siteQ.data!.zones} frame={detections[c.name]} streamOn={!!streamOn.data} />
            ))}
          </div>
        )}
      </Panel>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Panel eyebrow={t("captions")} bodyClassName="max-h-[420px] overflow-y-auto">
          <CaptionTicker site={site} />
        </Panel>
        <Panel eyebrow={t("opinions")} sub={t("opinionsSub")} bodyClassName="max-h-[420px] overflow-y-auto">
          <OpinionPanel site={site} />
        </Panel>
      </div>
    </div>
  );
}
