"use client";

import { Fragment, useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { AskAnswer, AskCitation } from "@/lib/api";
import { fmtNumber, fmtPct } from "@/lib/format";
import { Chip } from "@/components/ui/panel";
import { CitationChip } from "./citation-chip";
import { ClipThumb } from "./clip-thumb";
import { FollowUps } from "./follow-ups";
import { cn } from "@/lib/utils";

const CITE = /\[c:([A-Za-z0-9\-_:]+)\]/g;

/** Answer text with [c:ID] markers turned into numbered superscript links to the matching chip. */
export function AnswerText({ text, citations, streaming = false }: { text: string; citations: AskCitation[]; streaming?: boolean }) {
  const order = useMemo(() => citations.map((c) => c.chunk_id), [citations]);
  const parts: React.ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  const re = new RegExp(CITE.source, "g");
  while ((m = re.exec(text))) {
    parts.push(text.slice(last, m.index));
    const i = order.indexOf(m[1]);
    parts.push(
      <sup key={`${m.index}-${m[1]}`} className="ms-0.5 font-mono text-[0.625rem] text-signal" data-testid="cite-ref" data-chunk={m[1]}>
        [{i >= 0 ? i + 1 : "?"}]
      </sup>,
    );
    last = m.index + m[0].length;
  }
  parts.push(text.slice(last));
  return (
    <p className={cn("text-[0.9375rem] leading-relaxed text-ink", streaming && "after:ms-0.5 after:inline-block after:h-4 after:w-0.5 after:animate-pulse after:bg-signal after:align-middle")} data-testid="answer-text">
      {parts.map((p, i) => (
        <Fragment key={i}>{p}</Fragment>
      ))}
    </p>
  );
}

export function AnswerCard({ answer, onFollowUp, busy }: { answer: AskAnswer; onFollowUp: (q: string) => void; busy?: boolean }) {
  const t = useTranslations("ask");
  const locale = useLocale();
  const clips = answer.citations.filter((c) => c.clip_url);
  const tone = answer.path === "model" ? "signal" : answer.path === "template" ? "neutral" : "warn";
  return (
    <article className="panel-raised flex flex-col gap-4 p-4" data-testid="answer-card" dir="auto">
      <header className="flex flex-wrap items-center gap-2">
        <h2 className="me-auto min-w-0 flex-1 truncate text-[0.9375rem] font-medium text-ink" dir="auto">{answer.q}</h2>
        <Chip tone={tone}>{t(`path.${answer.path}`)}</Chip>
        {answer.provider !== "none" && <Chip tone="neutral">{t("provider", { provider: answer.model || answer.provider })}</Chip>}
        <span className="font-mono text-[0.6875rem] text-ink-faint">
          {t("confidence")} {fmtPct(locale, answer.confidence, 0)} · {t("latency", { ms: fmtNumber(locale, answer.latency_ms) })}
        </span>
      </header>

      <AnswerText text={answer.text} citations={answer.citations} />

      {clips.length > 0 && (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {clips.slice(0, 4).map((c) => (
            <ClipThumb key={c.chunk_id} c={c} />
          ))}
        </div>
      )}

      {answer.citations.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="eyebrow">{t("sources", { n: answer.citations.length })}</span>
          <ul className="flex flex-wrap gap-1.5" data-testid="citations">
            {answer.citations.map((c, i) => (
              <li key={c.chunk_id} className="min-w-0">
                <CitationChip c={c} index={i} />
              </li>
            ))}
          </ul>
        </div>
      )}

      <FollowUps items={answer.followups} onPick={onFollowUp} disabled={busy} />
    </article>
  );
}
