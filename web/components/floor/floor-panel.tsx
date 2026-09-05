"use client";

import { useQuery } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";
import { useMemo } from "react";
import { api } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { ErrorState, Skeleton } from "@/components/ui/panel";
import { FlatPlan } from "./flat-plan";
import { useFloorEvents } from "./use-floor-events";

const FloorScene = dynamic(() => import("./floor-scene").then((m) => m.FloorScene), {
  ssr: false,
  loading: () => <Skeleton className="h-full w-full rounded-none" />,
});

function hasWebGL(): boolean {
  if (typeof document === "undefined") return false;
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

export function FloorPanel({ height = 420, full = false }: { height?: number; full?: boolean }) {
  const t = useTranslations("floor");
  const site = useAppStore((s) => s.site);
  const siteQ = useQuery({ queryKey: ["site", site], queryFn: () => api.site(site), enabled: !!site, staleTime: 5 * 60_000 });
  const { lastByZone, pulses } = useFloorEvents(site);
  const webgl = useMemo(() => hasWebGL(), []);

  if (siteQ.isPending) return <Skeleton className="w-full rounded-none" style={{ height }} />;
  if (siteQ.isError || !siteQ.data) return <ErrorState what={t("title").toLowerCase()} onRetry={() => siteQ.refetch()} />;
  const floor = siteQ.data.floor;

  return (
    <div className="relative w-full" style={{ height: full ? "calc(100dvh - 15rem)" : height, minHeight: 320 }}>
      {webgl ? (
        <FloorScene floor={floor} lastByZone={lastByZone} pulses={pulses} profile={siteQ.data.profile} />
      ) : (
        <>
          <FlatPlan floor={floor} lastByZone={lastByZone} />
          <p className="absolute bottom-2 start-3 font-mono text-[0.6875rem] text-ink-faint">{t("webgl")}</p>
        </>
      )}
      <Legend />
    </div>
  );
}

const ZONE_KINDS = ["entrance", "queue", "checkout", "shelf", "work_area", "exclusion", "machine"] as const;
export const ZONE_COLOR: Record<string, string> = {
  entrance: "var(--ink-faint)",
  queue: "var(--warn)",
  checkout: "var(--signal)",
  shelf: "var(--info)",
  work_area: "var(--ink-faint)",
  exclusion: "var(--critical)",
  machine: "var(--signal)",
};

function Legend() {
  const t = useTranslations("floor");
  const profile = useAppStore((s) => s.profile);
  const kinds = ZONE_KINDS.filter((k) => (profile === "retail" ? ["entrance", "queue", "checkout", "shelf"] : ["entrance", "work_area", "exclusion", "machine"]).includes(k));
  return (
    <ul aria-label={t("legend")} className="pointer-events-none absolute end-3 top-3 flex flex-col gap-1 rounded-md border border-hairline bg-surface/80 px-2 py-1.5 font-mono text-[0.625rem] text-ink-muted backdrop-blur-sm">
      {kinds.map((k) => (
        <li key={k} className="flex items-center gap-2">
          <span aria-hidden className="inline-block size-2 rounded-sm" style={{ background: ZONE_COLOR[k] }} />
          {t(`zone.${k}`)}
        </li>
      ))}
    </ul>
  );
}
