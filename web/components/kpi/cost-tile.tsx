"use client";

import { useQuery } from "@tanstack/react-query";
import { useLocale, useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { fmtNumber } from "@/lib/format";
import { KpiTile } from "./kpi-tile";

/** Cost per site per day: the sum of every model call's span. Stays $0 on the free providers. */
export function CostTile({ site }: { site: string }) {
  const t = useTranslations("kpi");
  const locale = useLocale();
  const cost = useQuery({ queryKey: ["cost", site], queryFn: () => api.cost(site, 1), enabled: !!site, refetchInterval: 60_000 });
  const today = cost.data?.today;
  const providers = today ? Object.entries(today.providers).map(([k, v]) => `${k} ${v.requests}`).join(", ") : "";
  return (
    <KpiTile
      label={t("cost")}
      value={today ? today.usd : null}
      format={(n) => `$${fmtNumber(locale, n, 4)}`}
      loading={cost.isPending}
      sub={today && today.requests > 0 ? t("costSub", { requests: fmtNumber(locale, today.requests), tokens: fmtNumber(locale, today.tokens_in + today.tokens_out), providers }) : t("costNone")}
      tone={today && today.usd > 0 ? "warn" : "ok"}
    />
  );
}
