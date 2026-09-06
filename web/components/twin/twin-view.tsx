"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import dynamic from "next/dynamic";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { fmtNumber, fmtPct } from "@/lib/format";
import { useAppStore } from "@/lib/store";
import { useNow } from "@/lib/use-now";
import { binLabel, clampBin, eventsAt, occupancyAt } from "@/lib/twin-math";
import { Button } from "@/components/ui/button";
import { Chip, EmptyState, ErrorState, Panel, Skeleton } from "@/components/ui/panel";
import { DeltaCard } from "./delta-card";
import { Scrubber } from "./scrubber";
import { WhatIfPanel, type WhatIfInputs } from "./what-if-panel";

const FloorScene = dynamic(() => import("@/components/floor/floor-scene").then((m) => m.FloorScene), { ssr: false, loading: () => <Skeleton className="h-full w-full rounded-none" /> });

const yesterday = () => new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);

export function TwinView() {
  const t = useTranslations("twin");
  const tk = useTranslations("kind");
  const locale = useLocale();
  const site = useAppStore((s) => s.site);
  const [day, setDay] = useState(yesterday);
  const [bin, setBinState] = useState(12 * 60);
  const [inputs, setInputs] = useState<WhatIfInputs>({ staff_delta: 0, express_lane: false });
  const setBin = useCallback((b: number) => setBinState(clampBin(b)), []);
  const now = useNow(1000);
  const siteQ = useQuery({ queryKey: ["site", site], queryFn: () => api.site(site), enabled: !!site, staleTime: 5 * 60_000 });
  const replay = useQuery({ queryKey: ["twin", site, day], queryFn: () => api.twinReplay(site, day), enabled: !!site });
  const whatif = useQuery({
    queryKey: ["twin-whatif", site, day, inputs.staff_delta, inputs.express_lane],
    queryFn: () => api.twinWhatIf({ site, date: day, staff_delta: inputs.staff_delta, zone_changes: { express_lane: inputs.express_lane } }),
    enabled: !!site,
  });
  const save = useMutation({
    mutationFn: async () => {
      const w = whatif.data!;
      const md = [`# Scenario ${day}: ${inputs.staff_delta >= 0 ? "+" : ""}${inputs.staff_delta} tills${inputs.express_lane ? ", express lane" : ""}`, "",
        `Site ${site}. What-if on the replay of ${day} with ${w.baseline_tills} baseline tills and μ ${w.mu_per_h}/h per till (${w.mu_source}).`, "",
        "## Before", `Staff-hours ${w.before!.staff_hours}, customer wait ${w.before!.customer_wait_min} min, mean W_q ${w.before!.mean_wq_min} min, model service level ${Math.round(w.before!.service_level_model * 100)}%, peak ρ ${w.before!.peak_rho}.`, "",
        "## After", `Staff-hours ${w.after!.staff_hours}, customer wait ${w.after!.customer_wait_min} min, mean W_q ${w.after!.mean_wq_min} min, model service level ${Math.round(w.after!.service_level_model * 100)}%, peak ρ ${w.after!.peak_rho}.`, "",
        "## Delta", `Customer wait ${w.delta!.wait_reduction_pct}% lower for ${w.delta!.staff_hours >= 0 ? "+" : ""}${w.delta!.staff_hours} staff-hours.`, "",
        "## MILP plan", `Staff-hours ${w.milp!.staff_hours}, customer wait ${w.milp!.customer_wait_min} min, peak tills ${Math.max(...w.milp!.tills)}.`].join("\n");
      return api.uploadDocument(site, "scenario", `Scenario ${day} ${inputs.staff_delta >= 0 ? "+" : ""}${inputs.staff_delta} tills${inputs.express_lane ? " express" : ""}`, `scenario-${day}.md`, md);
    },
  });
  const occupancy = useMemo(() => (replay.data ? occupancyAt(replay.data, bin) : undefined), [replay.data, bin]);
  const atMinute = replay.data ? eventsAt(replay.data, bin) : [];
  const empty = replay.data && replay.data.totals.events === 0 && replay.data.totals.arrivals === 0;

  return (
    <div className="flex flex-col gap-3">
      <h1 className="sr-only">{t("title")}</h1>
      <Panel eyebrow={t("title")} sub={t("sub")} actions={
        <label className="flex items-center gap-2 text-xs text-ink-muted">
          {t("day")} <input type="date" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} className="h-8 rounded-md border border-hairline-strong bg-surface px-2 font-mono text-[0.75rem] text-ink" data-testid="day" />
        </label>
      } bodyClassName="relative">
        <div className="relative w-full" style={{ height: "min(56dvh, 520px)", minHeight: 320 }}>
          {siteQ.data && <FloorScene floor={siteQ.data.floor} lastByZone={{}} pulses={atMinute.map((e) => ({ id: e.id, zone: e.zone ?? "entrance", severity: e.severity, at: now }))} profile={siteQ.data.profile} occupancy={occupancy} />}
          <div className="absolute end-3 top-3 rounded-md bg-ground/80 px-2 py-1 font-mono text-[0.6875rem] text-ink" data-testid="clock-overlay">{day} {binLabel(bin)}</div>
        </div>
        <div className="border-t border-hairline p-3">
          {replay.isPending ? <Skeleton className="h-24" /> : replay.isError ? <ErrorState what={t("title").toLowerCase()} onRetry={() => replay.refetch()} /> : empty ? <EmptyState title={t("noEvents")} /> : (
            <Scrubber bin={bin} onBin={setBin} arrivals={replay.data!.arrivals} queue={replay.data!.queue} events={replay.data!.events} />
          )}
        </div>
      </Panel>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-12">
        <Panel eyebrow={t("eventsAt")} className="lg:col-span-4" bodyClassName="max-h-72 overflow-y-auto">
          {atMinute.length === 0 ? <EmptyState title="–" /> : (
            <ul className="divide-y divide-hairline">{atMinute.map((e) => <li key={e.id} className="flex items-center gap-2 px-3 py-2 text-[0.8125rem]"><Chip tone={e.severity === 3 ? "critical" : e.severity === 2 ? "warn" : "neutral"}>S{e.severity}</Chip><span className="text-ink">{tk.has(e.kind) ? tk(e.kind as Parameters<typeof tk>[0]) : e.kind}</span><span className="ms-auto font-mono text-[0.6875rem] text-ink-faint">{binLabel(e.min)} · {e.zone ?? "-"}</span></li>)}</ul>
          )}
        </Panel>
        <Panel eyebrow={t("totals")} className="lg:col-span-4" bodyClassName="p-3">
          {replay.data && (
            <dl className="grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-[0.75rem]">
              <dt className="text-ink-faint">{t("arrivals")}</dt><dd className="text-ink">{fmtNumber(locale, replay.data.totals.arrivals)}</dd>
              <dt className="text-ink-faint">{t("served")}</dt><dd className="text-ink">{fmtNumber(locale, replay.data.totals.served)}</dd>
              <dt className="text-ink-faint">{t("peakQueue")}</dt><dd className="text-ink">{fmtNumber(locale, replay.data.totals.peak_queue)}</dd>
              <dt className="text-ink-faint">{t("busiestMinute")}</dt><dd className="text-ink">{replay.data.totals.busiest_minute !== null ? binLabel(replay.data.totals.busiest_minute) : "–"}</dd>
              {Object.entries(replay.data.totals.shelf_availability).map(([s, v]) => <><dt key={`k${s}`} className="text-ink-faint">{t("shelf")} {s}</dt><dd key={`v${s}`} className="text-ink">{fmtPct(locale, v, 1)}</dd></>)}
            </dl>
          )}
        </Panel>
        <Panel eyebrow={t("whatIf")} className="lg:col-span-4">
          <WhatIfPanel value={inputs} onChange={setInputs} disabled={whatif.isPending} />
        </Panel>
        <Panel eyebrow={`${t("before")} → ${t("after")}`} className="lg:col-span-12" actions={
          <Button variant="outline" onClick={() => save.mutate()} busy={save.isPending} disabled={!whatif.data?.sufficient || save.isPending} data-testid="save-scenario">
            {save.isPending ? t("saving") : save.isSuccess ? t("saved") : t("save")}
          </Button>
        }>
          {whatif.isPending ? <Skeleton className="h-40 m-3" /> : whatif.isError ? <ErrorState what={t("whatIf").toLowerCase()} onRetry={() => whatif.refetch()} /> : <DeltaCard w={whatif.data!} />}
        </Panel>
      </div>
    </div>
  );
}
