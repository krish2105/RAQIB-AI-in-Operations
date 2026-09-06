"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { ErrorState, Panel, Skeleton } from "@/components/ui/panel";
import { AgentCard } from "./agent-card";
import { KillSwitch } from "./kill-switch";
import { MessageLog } from "./message-log";
import { RunGraph } from "./run-graph";

export function CrewView() {
  const t = useTranslations("crew");
  const site = useAppStore((s) => s.site);
  const roster = useQuery({ queryKey: ["crew", site, "roster"], queryFn: () => api.crewRoster(site), enabled: !!site, refetchInterval: 10_000 });
  const messages = useQuery({ queryKey: ["crew", site, "messages"], queryFn: () => api.crewMessages(site, 100), enabled: !!site, refetchInterval: 10_000 });
  const disabled = roster.isError && (roster.error as { status?: number }).status === 503;
  return (
    <div className="flex flex-col gap-3">
      <h1 className="sr-only">{t("title")}</h1>
      <Panel eyebrow={t("kill")} className="border-critical/20">
        <KillSwitch site={site} />
      </Panel>
      <Panel eyebrow={t("roster")} sub={t("sub")} bodyClassName="p-3">
        {roster.isPending ? <Skeleton className="h-40" /> : disabled ? <p className="text-sm text-critical">{t("disabled")}</p> : roster.isError ? <ErrorState what={t("roster").toLowerCase()} onRetry={() => roster.refetch()} /> : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {roster.data.map((a) => <AgentCard key={a.name} a={a} />)}
          </div>
        )}
      </Panel>
      <Panel eyebrow={t("graph")} sub={t("graphSub")} bodyClassName="p-1">
        {roster.data && messages.data ? <RunGraph roster={roster.data} messages={messages.data} /> : <Skeleton className="h-[520px]" />}
      </Panel>
      <Panel eyebrow={t("messages")} sub={t("messagesSub")} bodyClassName="max-h-[520px] overflow-y-auto">
        {messages.isPending ? <Skeleton className="h-24 m-3" /> : messages.isError ? <ErrorState what={t("messages").toLowerCase()} onRetry={() => messages.refetch()} /> : <MessageLog messages={messages.data} />}
      </Panel>
    </div>
  );
}
