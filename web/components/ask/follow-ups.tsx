"use client";

import { CornerDownRight } from "lucide-react";
import { useTranslations } from "next-intl";

export function FollowUps({ items, onPick, disabled }: { items: string[]; onPick: (q: string) => void; disabled?: boolean }) {
  const t = useTranslations("ask");
  if (!items.length) return null;
  return (
    <div className="flex flex-col gap-1.5">
      <span className="eyebrow">{t("followups")}</span>
      <ul className="flex flex-wrap gap-2">
        {items.slice(0, 3).map((q) => (
          <li key={q}>
            <button type="button" onClick={() => onPick(q)} disabled={disabled} className="inline-flex max-w-[26rem] items-center gap-1.5 rounded-full border border-hairline px-3 py-1 text-start text-[0.8125rem] text-ink-muted hover:border-signal/40 hover:text-ink disabled:opacity-50">
              <CornerDownRight className="size-3.5 shrink-0 rtl:-scale-x-100" aria-hidden />
              <span className="truncate">{q}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
