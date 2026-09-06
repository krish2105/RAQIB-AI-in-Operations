"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { api, type PolicyValues } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { Chip, ErrorState, Panel, Skeleton } from "@/components/ui/panel";

export const FIELDS: Array<{ key: keyof PolicyValues; min: number; max: number; step: number }> = [
  { key: "rho_threshold", min: 0.51, max: 0.99, step: 0.01 },
  { key: "review_confidence", min: 0, max: 1, step: 0.05 },
  { key: "work_order_cooldown_h", min: 0, max: 48, step: 0.5 },
  { key: "vlm_review_confidence", min: 0, max: 1, step: 0.05 },
];

/** Pure diff between the stored values and the draft; the API computes the same thing server-side and returns it after the write. */
export function policyDiff(before: PolicyValues, after: PolicyValues): Record<string, { before: number; after: number }> {
  const out: Record<string, { before: number; after: number }> = {};
  for (const f of FIELDS) if (before[f.key] !== after[f.key]) out[f.key] = { before: before[f.key], after: after[f.key] };
  return out;
}

export function PolicyEditor() {
  const t = useTranslations("security");
  const site = useAppStore((s) => s.site);
  const qc = useQueryClient();
  const me = useQuery({ queryKey: ["me"], queryFn: api.me, retry: false, staleTime: 60_000 });
  const policy = useQuery({ queryKey: ["policy", site], queryFn: () => api.policy(site), enabled: !!site });
  // The draft is an override of the stored values; null means "no local edits", so a refetch after a save shows the new values.
  const [edits, setDraft] = useState<PolicyValues | null>(null);
  const [reviewing, setReviewing] = useState(false);
  const [note, setNote] = useState("");
  const draft = edits ?? policy.data?.values ?? null;
  const save = useMutation({
    mutationFn: (v: PolicyValues) => api.putPolicy(site, v, note),
    onSuccess: () => {
      setReviewing(false);
      setNote("");
      setDraft(null);
      qc.invalidateQueries({ queryKey: ["policy", site] });
    },
  });
  const canEdit = me.data?.capabilities?.policy === true;
  const diff = policy.data && draft ? policyDiff(policy.data.values, draft) : {};
  const changed = Object.keys(diff).length > 0;

  return (
    <Panel eyebrow={t("policy")} sub={t("policySub")} className="h-full" actions={me.data && !canEdit ? <Chip tone="neutral" data-testid="policy-readonly">{t("readOnly")}</Chip> : null}>
      {policy.isPending || !draft ? <Skeleton className="m-3 h-40" /> : policy.isError ? <ErrorState what={t("policy").toLowerCase()} onRetry={() => policy.refetch()} /> : (
        <form className="flex flex-col gap-3 p-3" data-testid="policy-editor" data-readonly={!canEdit} onSubmit={(e) => { e.preventDefault(); if (changed) setReviewing(true); }}>
          {FIELDS.map((f) => (
            <label key={f.key} className="grid grid-cols-[1fr_auto] items-center gap-x-3 gap-y-0.5 text-[0.8125rem] text-ink">
              <span>{t(`fields.${f.key}`)}</span>
              <input
                type="number" inputMode="decimal" min={f.min} max={f.max} step={f.step} value={draft[f.key]} disabled={!canEdit} readOnly={!canEdit}
                aria-label={t(`fields.${f.key}`)} data-testid={`policy-${f.key}`}
                onChange={(e) => setDraft({ ...draft, [f.key]: Number(e.target.value) })}
                className="h-8 w-24 rounded-md border border-hairline-strong bg-surface px-2 text-end font-mono text-[0.75rem] text-ink disabled:opacity-60"
              />
              <span className="col-span-2 font-mono text-[0.625rem] text-ink-faint">{t("default", { v: policy.data.defaults[f.key] })}{policy.data.values[f.key] !== policy.data.defaults[f.key] ? ` · ${policy.data.values[f.key]}` : ""}</span>
            </label>
          ))}
          <div className="flex flex-wrap items-center gap-2">
            {canEdit && <Button type="submit" variant="primary" disabled={!changed} data-testid="policy-review">{t("review")}</Button>}
            {!changed && canEdit && <span className="text-xs text-ink-faint">{t("noChanges")}</span>}
            {policy.data.updated_by && <span className="font-mono text-[0.6875rem] text-ink-faint">{t("updatedBy", { by: policy.data.updated_by })}</span>}
            {save.isSuccess && <Chip tone="ok" data-testid="policy-saved">{t("saved", { by: save.data.updated_by })}</Chip>}
            {save.isError && <Chip tone="critical">{(save.error as Error).message}</Chip>}
          </div>
          {reviewing && changed && (
            <section className="flex flex-col gap-2 rounded-md border border-hairline-strong bg-raised/50 p-3" data-testid="policy-diff" aria-label={t("diff")}>
              <span className="font-mono text-[0.6875rem] uppercase tracking-wider text-ink-faint">{t("diff")}</span>
              <ul className="flex flex-col gap-1 font-mono text-[0.75rem]">
                {Object.entries(diff).map(([k, d]) => (
                  <li key={k} className="flex flex-wrap items-baseline gap-2" data-testid={`diff-${k}`}>
                    <span className="text-ink">{t(`fields.${k}`)}</span>
                    <span className="text-ink-faint">{t("before")}</span><span className="text-critical line-through">{d.before}</span>
                    <span className="text-ink-faint">{t("after")}</span><span className="text-ok">{d.after}</span>
                  </li>
                ))}
              </ul>
              <input value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("note")} aria-label={t("note")} data-testid="policy-note" className="h-8 rounded-md border border-hairline-strong bg-surface px-2 text-[0.8125rem] text-ink" />
              <div className="flex gap-2">
                <Button type="button" variant="primary" busy={save.isPending} disabled={save.isPending} onClick={() => save.mutate(draft)} data-testid="policy-confirm">{save.isPending ? t("saving") : t("confirm")}</Button>
                <Button type="button" onClick={() => { setReviewing(false); setDraft(null); }} data-testid="policy-cancel">{t("cancel")}</Button>
              </div>
            </section>
          )}
        </form>
      )}
    </Panel>
  );
}
