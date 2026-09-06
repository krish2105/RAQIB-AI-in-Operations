"use client";

import { useLocale, useTranslations } from "next-intl";
import type { CrewMessage } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { Chip, EmptyState } from "@/components/ui/panel";

export function MessageLog({ messages }: { messages: CrewMessage[] }) {
  const t = useTranslations("crew");
  const locale = useLocale();
  if (!messages.length) return <EmptyState title={t("empty")} />;
  return (
    <ul className="divide-y divide-hairline" data-testid="message-log">
      {messages.map((m) => (
        <li key={m.id} className="flex flex-col gap-1 px-3 py-2 text-[0.8125rem]">
          <div className="flex flex-wrap items-center gap-2 font-mono text-[0.6875rem]">
            <span className="text-ink">{m.from} → {m.to}</span>
            <Chip tone="neutral">{m.schema}</Chip>
            <Chip tone={m.verified ? "ok" : "critical"}>{m.verified ? t("verified") : t("tampered")}</Chip>
            <span className="text-ink-faint">{m.hmac}</span>
            <span className="ms-auto text-ink-faint">{fmtDateTime(locale, m.ts)}</span>
          </div>
          <pre className="max-h-24 overflow-auto rounded bg-sunken p-2 font-mono text-[0.6875rem] text-ink-muted">{JSON.stringify(m.payload)}</pre>
        </li>
      ))}
    </ul>
  );
}
