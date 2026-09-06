"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { Chip, EmptyState, Skeleton } from "@/components/ui/panel";

const ROLES = ["floor_manager", "store_manager", "safety_officer", "maintenance", "shift_supervisor"];

export function NotifyPanel() {
  const t = useTranslations("settings");
  const site = useAppStore((s) => s.site);
  const qc = useQueryClient();
  const [form, setForm] = useState({ phone: "", role: "floor_manager", lang: "en" });
  const status = useQuery({ queryKey: ["integrations-status"], queryFn: api.integrationStatus, staleTime: 60_000 });
  const optins = useQuery({ queryKey: ["optins", site], queryFn: () => api.optins(site), enabled: !!site });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["optins", site] });
  const add = useMutation({ mutationFn: () => api.optIn({ site, ...form }), onSuccess: () => { setForm((f) => ({ ...f, phone: "" })); invalidate(); } });
  const remove = useMutation({ mutationFn: (id: number) => api.optOut(id), onSuccess: invalidate });
  const s = status.data;
  return (
    <div className="flex flex-col gap-4 p-3" data-testid="notify-panel">
      <section className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-[0.9375rem] font-medium text-ink">{t("whatsapp")}</h3>
          {s && <Chip tone={s.whatsapp.configured ? "ok" : "neutral"}>{s.whatsapp.configured ? t("configured") : t("notConfigured")}</Chip>}
          {s && <Chip tone="neutral">{t("templates")} · {s.whatsapp.templates.length} × {s.whatsapp.languages.join("/")}</Chip>}
        </div>
        <p className="text-xs text-ink-muted">{t("whatsappSub")}</p>
        <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); if (form.phone.trim()) add.mutate(); }}>
          <label className="flex flex-col gap-1 text-[0.6875rem] text-ink-faint">{t("phone")}<input value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="+971 50 000 0000" className="h-9 w-44 rounded-md border border-hairline-strong bg-surface px-2 font-mono text-[0.8125rem] text-ink" data-testid="optin-phone" /></label>
          <label className="flex flex-col gap-1 text-[0.6875rem] text-ink-faint">{t("role")}<select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} className="h-9 rounded-md border border-hairline-strong bg-surface px-2 font-mono text-[0.75rem] text-ink">{ROLES.map((r) => <option key={r} value={r}>{r}</option>)}</select></label>
          <label className="flex flex-col gap-1 text-[0.6875rem] text-ink-faint">{t("lang")}<select value={form.lang} onChange={(e) => setForm({ ...form, lang: e.target.value })} className="h-9 rounded-md border border-hairline-strong bg-surface px-2 font-mono text-[0.75rem] text-ink">{["en", "hi", "ar"].map((l) => <option key={l} value={l}>{l}</option>)}</select></label>
          <Button type="submit" variant="outline" busy={add.isPending} disabled={add.isPending || !form.phone.trim()} data-testid="optin-add">{t("add")}</Button>
          {add.isError && <Chip tone="critical">{(add.error as Error).message}</Chip>}
        </form>
        {optins.isPending ? <Skeleton className="h-12" /> : !optins.data?.length ? <EmptyState title={t("noOptins")} /> : (
          <ul className="divide-y divide-hairline" data-testid="optin-list">
            {optins.data.map((o) => (
              <li key={o.id} className="flex items-center gap-2 py-1.5 font-mono text-[0.75rem]"><span className="text-ink">{o.phone}</span><Chip tone="neutral">{o.role}</Chip><Chip tone="neutral">{o.lang}</Chip>
                <button type="button" onClick={() => remove.mutate(o.id)} className="ms-auto text-[0.6875rem] text-ink-faint hover:text-critical">{t("remove")}</button></li>
            ))}
          </ul>
        )}
      </section>
      {s && (
        <section className="flex flex-wrap gap-2 text-[0.75rem]">
          <Chip tone={s.greenlam.configured ? "ok" : "neutral"}>{t("greenlam")} · {s.greenlam.configured ? t("configured") : t("notConfigured")} · {s.greenlam.retries} {t("retries")} · {t("breaker", { n: s.greenlam.breaker.failures, s: s.greenlam.breaker.cooldown_s })}</Chip>
          <Chip tone={s.webhook.configured ? "ok" : "neutral"}>{t("webhook")} · {s.webhook.configured ? t("configured") : t("notConfigured")}</Chip>
          <Chip tone={s.stream.configured ? "ok" : "neutral"}>{t("stream")} · {s.stream.configured ? t("configured") : t("notConfigured")}</Chip>
          <span className="basis-full text-[0.6875rem] text-ink-faint">{t("envHint")}</span>
        </section>
      )}
    </div>
  );
}
