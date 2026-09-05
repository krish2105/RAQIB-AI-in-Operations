"use client";

import { useQuery } from "@tanstack/react-query";
import { Languages, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useLocale, useTranslations } from "next-intl";
import { useEffect } from "react";
import { usePathname, useRouter } from "@/i18n/navigation";
import { useMounted } from "@/lib/use-now";
import { routing } from "@/i18n/routing";
import { api } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import { cn } from "@/lib/utils";
import { Wordmark } from "./rail";

const LOCALE_LABEL: Record<string, string> = { en: "EN", hi: "हिं", ar: "ع" };

export function Header() {
  const t = useTranslations("header");
  const tb = useTranslations("brand");
  const { site, profile, live, setSite } = useAppStore();
  const sites = useQuery({ queryKey: ["sites"], queryFn: api.sites, staleTime: 5 * 60_000 });
  const kpis = useQuery({ queryKey: ["kpis", site], queryFn: () => api.kpis(site), enabled: !!site });

  // If the persisted site no longer exists on this API, snap to the first one.
  useEffect(() => {
    if (sites.data && sites.data.length && !sites.data.some((s) => s.name === site)) {
      setSite(sites.data[0].name, sites.data[0].profile);
    }
  }, [sites.data, site, setSite]);

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-hairline bg-ground/85 px-3 backdrop-blur-md sm:px-5">
      <div className="lg:hidden">
        <Wordmark profile={profile} retail={tb("retail")} retailAr={tb("retailArabic")} factory={tb("factory")} factoryAr={tb("factoryArabic")} />
      </div>

      <label className="ms-auto flex items-center gap-2 text-xs text-ink-muted lg:ms-0">
        <span className="eyebrow hidden sm:inline">{t("site")}</span>
        <select
          value={site}
          onChange={(e) => {
            const s = sites.data?.find((x) => x.name === e.target.value);
            if (s) setSite(s.name, s.profile);
          }}
          className="h-8 max-w-[11rem] rounded-md border border-hairline-strong bg-surface px-2 font-mono text-[0.75rem] text-ink"
          aria-label={t("site")}
        >
          {(sites.data ?? [{ name: site, profile }]).map((s) => (
            <option key={s.name} value={s.name}>
              {s.name} · {s.profile}
            </option>
          ))}
        </select>
      </label>

      <LivePill state={live} labels={{ live: t("live"), connecting: t("connecting"), reconnecting: t("reconnecting"), off: t("offline") }} />

      {kpis.data && kpis.data.simulated_share > 0 && (
        <span className="hidden items-center gap-1.5 rounded-full border border-hairline px-2 py-0.5 font-mono text-[0.6875rem] text-ink-muted md:inline-flex" title={t("simulated")}>
          <span aria-hidden className="size-1.5 rounded-full bg-info" />
          {t("simulated")}
        </span>
      )}

      <div className="ms-auto flex items-center gap-1">
        <LocaleSwitch />
        <ThemeToggle />
      </div>
    </header>
  );
}

function LivePill({ state, labels }: { state: string; labels: Record<string, string> }) {
  return (
    <span className="inline-flex h-7 items-center gap-2 rounded-full border border-hairline px-2.5 font-mono text-[0.6875rem] uppercase tracking-wider text-ink-muted" role="status" aria-live="polite">
      <span className="live-dot" data-state={state === "live" ? "on" : "off"} aria-hidden />
      {labels[state] ?? state}
    </span>
  );
}

export function ThemeToggle() {
  const t = useTranslations("header");
  const { resolvedTheme, setTheme } = useTheme();
  const mounted = useMounted();
  const dark = mounted ? resolvedTheme !== "light" : true;
  return (
    <button
      onClick={() => setTheme(dark ? "light" : "dark")}
      aria-label={t("theme")}
      aria-pressed={!dark}
      title={dark ? t("themeLight") : t("themeDark")}
      className="relative flex size-9 items-center justify-center rounded-md text-ink-muted hover:bg-raised hover:text-ink"
    >
      <Sun className={cn("absolute size-[18px] transition-all duration-300", dark ? "scale-0 rotate-90 opacity-0" : "scale-100 rotate-0 opacity-100")} strokeWidth={1.75} aria-hidden />
      <Moon className={cn("absolute size-[18px] transition-all duration-300", dark ? "scale-100 rotate-0 opacity-100" : "scale-0 -rotate-90 opacity-0")} strokeWidth={1.75} aria-hidden />
    </button>
  );
}

export function LocaleSwitch() {
  const t = useTranslations("header");
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();
  return (
    <label className="flex items-center gap-1 text-ink-muted">
      <Languages className="size-4" strokeWidth={1.75} aria-hidden />
      <select
        value={locale}
        aria-label={t("language")}
        onChange={(e) => router.replace(pathname, { locale: e.target.value as (typeof routing.locales)[number] })}
        className="h-8 rounded-md border border-transparent bg-transparent px-1 font-mono text-[0.75rem] text-ink hover:border-hairline-strong"
      >
        {routing.locales.map((l) => (
          <option key={l} value={l}>
            {LOCALE_LABEL[l]}
          </option>
        ))}
      </select>
    </label>
  );
}
