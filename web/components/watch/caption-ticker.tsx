"use client";

import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api";
import { fmtTime } from "@/lib/format";
import { EmptyState, Skeleton } from "@/components/ui/panel";

export function CaptionTicker({ site }: { site: string }) {
  const t = useTranslations("watch");
  const locale = useLocale();
  const caps = useQuery({ queryKey: ["captions", site], queryFn: () => api.captions(site, 30), enabled: !!site, refetchInterval: 20_000 });
  if (caps.isPending) return <Skeleton className="h-24" />;
  if (!caps.data?.length) return <EmptyState title={t("captionsEmpty")} />;
  return (
    <ul className="divide-y divide-hairline" data-testid="caption-ticker">
      {caps.data.map((c) => (
        <li key={c.id} className="flex items-start gap-3 px-3 py-2 text-[0.8125rem]">
          <span className="shrink-0 font-mono text-[0.6875rem] text-ink-faint">{fmtTime(locale, c.ts)} · {c.camera}</span>
          <Link href={`/events/${c.event_id}`} className="min-w-0 flex-1 text-ink hover:underline" dir="auto">{c.text}</Link>
        </li>
      ))}
    </ul>
  );
}
