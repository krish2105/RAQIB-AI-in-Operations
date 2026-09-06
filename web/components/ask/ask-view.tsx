"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquareText, Sparkles } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAskStream } from "@/lib/ask-stream";
import { fmtRelative } from "@/lib/format";
import { useAppStore } from "@/lib/store";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorState, Panel, Skeleton } from "@/components/ui/panel";
import { AnswerCard, AnswerText } from "./answer-card";
import { AskBox } from "./ask-box";

export function AskView() {
  const t = useTranslations("ask");
  const locale = useLocale();
  const site = useAppStore((s) => s.site);
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const { state, ask, stop } = useAskStream();
  const history = useQuery({ queryKey: ["ask-history", site], queryFn: () => api.askHistory(site, 12), enabled: !!site });
  const index = useMutation({ mutationFn: () => api.index(site, 21), onSuccess: () => qc.invalidateQueries({ queryKey: ["ask-history", site] }) });
  const busy = state.stage === "planning" || state.stage === "retrieving" || state.stage === "answering";
  const submit = (text = q) => {
    const v = text.trim();
    if (!v) return;
    setQ(v);
    ask(v, site, locale);
    setTimeout(() => qc.invalidateQueries({ queryKey: ["ask-history", site] }), 1500);
  };
  const examples = t.raw("examples") as string[];
  const stageLabel = state.stage === "planning" ? t("planning") : state.stage === "retrieving" ? t("retrieving") : state.stage === "answering" ? t("answering") : null;

  return (
    <div className="flex flex-col gap-3">
      <h1 className="sr-only">{t("title")}</h1>
      <AskBox value={q} onChange={setQ} onSubmit={() => submit()} onStop={stop} busy={busy} />

      {state.stage === "idle" && (
        <Panel eyebrow={t("examplesTitle")} sub={t("sub")} bodyClassName="p-3">
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {examples.map((ex) => (
              <li key={ex}>
                <button type="button" onClick={() => submit(ex)} className="panel-raised flex h-full w-full items-start gap-2 p-3 text-start text-[0.8125rem] text-ink-muted hover:border-signal/40 hover:text-ink" data-testid="example">
                  <Sparkles className="mt-0.5 size-3.5 shrink-0 text-signal" aria-hidden />
                  <span dir="auto">{ex}</span>
                </button>
              </li>
            ))}
          </ul>
          <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-hairline pt-3 text-xs text-ink-muted">
            <span>{t("indexHint")}</span>
            <Button variant="outline" onClick={() => index.mutate()} busy={index.isPending} disabled={index.isPending} data-testid="index">
              {index.isPending ? t("indexing") : index.data ? t("indexed", { chunks: index.data.chunks }) : t("index")}
            </Button>
          </div>
        </Panel>
      )}

      {busy && (
        <article className="panel-raised flex flex-col gap-3 p-4" aria-live="polite" data-testid="answer-pending">
          <header className="flex items-center gap-2">
            <h2 className="me-auto truncate text-[0.9375rem] font-medium text-ink" dir="auto">{state.q}</h2>
            <span className="inline-flex items-center gap-2 font-mono text-[0.6875rem] text-ink-muted">
              <span aria-hidden className="size-2 animate-pulse rounded-full bg-signal" /> {stageLabel}
            </span>
          </header>
          {state.text ? <AnswerText text={state.text} citations={[]} streaming /> : <Skeleton className="h-16" />}
        </article>
      )}

      {state.stage === "error" && (
        <div className="panel">
          <ErrorState what={t("title").toLowerCase()} onRetry={() => submit(state.q)} />
        </div>
      )}

      {state.stage === "done" && state.answer && <AnswerCard answer={state.answer} onFollowUp={(f) => submit(f)} busy={busy} />}

      <Panel eyebrow={t("history")} bodyClassName="p-2">
        {history.isPending ? (
          <Skeleton className="h-16" />
        ) : history.isError ? (
          <ErrorState what={t("history").toLowerCase()} onRetry={() => history.refetch()} />
        ) : !history.data?.length ? (
          <EmptyState title={t("historyEmpty")} icon={<MessageSquareText className="size-6" strokeWidth={1.5} />} />
        ) : (
          <ul className="divide-y divide-hairline">
            {history.data.map((h) => (
              <li key={h.id}>
                <button type="button" onClick={() => submit(h.q)} className="flex w-full items-center gap-3 px-2 py-2 text-start hover:bg-raised">
                  <span className="min-w-0 flex-1 truncate text-[0.8125rem] text-ink" dir="auto">{h.q}</span>
                  <span className="font-mono text-[0.625rem] text-ink-faint">{h.citations.length} · {fmtRelative(locale, h.ts)}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
