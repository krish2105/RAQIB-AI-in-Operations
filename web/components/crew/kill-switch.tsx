"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { api } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/panel";

/** Admin-only in Phase J; today anyone can flip it, but only by typing KILL. */
export function KillSwitch({ site }: { site: string }) {
  const t = useTranslations("crew");
  const locale = useLocale();
  const qc = useQueryClient();
  const [typed, setTyped] = useState("");
  const [note, setNote] = useState("");
  const status = useQuery({ queryKey: ["crew", site, "status"], queryFn: api.crewStatus, refetchInterval: 15_000 });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["crew", site] });
  const kill = useMutation({ mutationFn: () => api.crewKill("admin", note, typed), onSuccess: () => { setTyped(""); invalidate(); } });
  const resume = useMutation({ mutationFn: () => api.crewResume("admin"), onSuccess: invalidate });
  const enabled = status.data?.agents_enabled ?? true;
  return (
    <div className="flex flex-col gap-3 p-3" data-testid="kill-switch" data-enabled={enabled}>
      <div className="flex flex-wrap items-center gap-2">
        <Chip tone={enabled ? "ok" : "critical"}>{enabled ? t("enabled") : t("disabled")}</Chip>
        {status.data?.flag && <span className="font-mono text-[0.6875rem] text-ink-faint">{t("by", { who: status.data.flag.updated_by })} · {fmtDateTime(locale, status.data.flag.updated_at)}{status.data.flag.note ? ` · ${status.data.flag.note}` : ""}</span>}
      </div>
      <p className="text-xs text-ink-muted">{t("killSub")}</p>
      {enabled ? (
        <form className="flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); if (typed === "KILL") kill.mutate(); }}>
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="note" className="h-9 w-40 rounded-md border border-hairline-strong bg-surface px-2 text-[0.8125rem] text-ink" aria-label="note" />
          <input value={typed} onChange={(e) => setTyped(e.target.value)} placeholder={t("killConfirm")} className="h-9 w-44 rounded-md border border-critical/40 bg-surface px-2 font-mono text-[0.8125rem] text-ink" aria-label={t("killConfirm")} data-testid="kill-confirm" />
          <Button type="submit" variant="danger" disabled={typed !== "KILL" || kill.isPending} busy={kill.isPending} data-testid="kill-button">
            {kill.isPending ? t("killing") : t("killButton")}
          </Button>
        </form>
      ) : status.data && !status.data.env_enabled ? (
        <p className="text-xs text-critical">{t("envLocked")}</p>
      ) : (
        <Button variant="primary" onClick={() => resume.mutate()} busy={resume.isPending} disabled={resume.isPending} data-testid="resume-button">
          {resume.isPending ? t("resuming") : t("resume")}
        </Button>
      )}
    </div>
  );
}
