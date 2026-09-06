"use client";

import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { API_URL, type AskCitation } from "@/lib/api";

/** Inline clip preview for a cited event that has a stored (blurred) clip. */
export function ClipThumb({ c }: { c: AskCitation }) {
  const t = useTranslations("ask");
  if (!c.clip_url || !c.event_id) return null;
  return (
    <Link href={`/events/${c.event_id}`} className="group relative block aspect-video w-40 shrink-0 overflow-hidden rounded-md border border-hairline bg-sunken" title={t("openEvent")}>
      <video src={`${API_URL}${c.clip_url}#t=0.5`} preload="metadata" muted playsInline className="size-full object-cover opacity-90 transition-opacity group-hover:opacity-100" />
      <span className="absolute bottom-1 start-1 rounded bg-ground/80 px-1.5 font-mono text-[0.625rem] text-ink">{t("clip")}</span>
    </Link>
  );
}
