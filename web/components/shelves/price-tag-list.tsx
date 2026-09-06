"use client";

import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import type { ShelfRow } from "@/lib/api";
import { fmtNumber, fmtTime } from "@/lib/format";

export function PriceTagList({ shelf }: { shelf: ShelfRow }) {
  const t = useTranslations("shelves");
  const locale = useLocale();
  if (!shelf.price_tags.length) return <p className="px-3 py-2 text-xs text-ink-muted">{t("noMismatch")}</p>;
  return (
    <table className="w-full font-mono text-[0.75rem]" data-testid={`price-tags-${shelf.shelf_id}`}>
      <thead><tr className="text-ink-faint"><th className="px-3 text-start font-normal">tag</th><th className="text-end font-normal">{t("read")}</th><th className="text-end font-normal">{t("expectedPrice")}</th><th className="px-3 text-end font-normal">{t("delta")}</th></tr></thead>
      <tbody>
        {shelf.price_tags.map((x) => (
          <tr key={x.event_id} className="border-t border-hairline">
            <td className="px-3 py-1 text-ink"><Link href={`/events/${x.event_id}`} className="hover:underline">{x.tag}</Link> <span className="text-ink-faint">{fmtTime(locale, x.ts)}</span></td>
            <td className="py-1 text-end text-ink">{fmtNumber(locale, x.read_price, 2)}</td>
            <td className="py-1 text-end text-ink">{fmtNumber(locale, x.expected_price, 2)}</td>
            <td className={`px-3 py-1 text-end ${Math.abs(x.delta) > 0 ? "text-warn" : "text-ok"}`}>{x.delta > 0 ? "+" : ""}{fmtNumber(locale, x.delta, 2)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
