"use client";

import { useTranslations } from "next-intl";
import { BarChart3, ChevronsLeft, ChevronsRight, FileText, LayoutDashboard, ListChecks, Map, PackageOpen } from "lucide-react";
import { Link, usePathname } from "@/i18n/navigation";
import { useAppStore } from "@/lib/store";
import { cn } from "@/lib/utils";

const ITEMS = [
  { href: "/", key: "dashboard", Icon: LayoutDashboard, profiles: ["retail", "factory"] },
  { href: "/floor", key: "floor", Icon: Map, profiles: ["retail", "factory"] },
  { href: "/actions", key: "actions", Icon: ListChecks, profiles: ["retail", "factory"] },
  { href: "/shelves", key: "shelves", Icon: PackageOpen, profiles: ["retail"] },
  { href: "/forecast", key: "forecast", Icon: BarChart3, profiles: ["retail", "factory"] },
  { href: "/report", key: "report", Icon: FileText, profiles: ["retail", "factory"] },
] as const;

export function Rail() {
  const t = useTranslations("nav");
  const tb = useTranslations("brand");
  const pathname = usePathname();
  const collapsed = useAppStore((s) => s.railCollapsed);
  const toggle = useAppStore((s) => s.toggleRail);
  const profile = useAppStore((s) => s.profile);
  const items = ITEMS.filter((i) => (i.profiles as readonly string[]).includes(profile));

  return (
    <>
      {/* Desktop rail */}
      <nav
        aria-label="Primary"
        className={cn(
          "hidden lg:flex fixed inset-y-0 start-0 z-30 flex-col border-e border-hairline bg-surface/95 backdrop-blur-sm transition-[width] duration-300 ease-[var(--ease-out-expo)]",
          collapsed ? "w-[var(--rail-w-collapsed)]" : "w-[var(--rail-w)]",
        )}
      >
        <div className={cn("flex h-14 items-center border-b border-hairline px-4", collapsed && "justify-center px-0")}>
          <Wordmark compact={collapsed} profile={profile} retail={tb("retail")} retailAr={tb("retailArabic")} factory={tb("factory")} factoryAr={tb("factoryArabic")} />
        </div>
        <ul className="flex flex-1 flex-col gap-1 p-2">
          {items.map(({ href, key, Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <li key={key}>
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  title={collapsed ? t(key) : undefined}
                  className={cn(
                    "group relative flex h-11 items-center gap-3 rounded-md px-3 text-[0.875rem] transition-colors",
                    active ? "bg-raised text-ink" : "text-ink-muted hover:bg-raised/70 hover:text-ink",
                    collapsed && "justify-center px-0",
                  )}
                >
                  {active && <span aria-hidden className="absolute inset-y-2 start-0 w-0.5 rounded-full bg-signal" />}
                  <Icon className="size-[18px] shrink-0" strokeWidth={1.75} aria-hidden />
                  {!collapsed && <span className="truncate">{t(key)}</span>}
                </Link>
              </li>
            );
          })}
        </ul>
        <div className="border-t border-hairline p-2">
          <button
            onClick={toggle}
            aria-label={collapsed ? t("expand") : t("collapse")}
            className="flex h-10 w-full items-center justify-center rounded-md text-ink-faint hover:bg-raised hover:text-ink"
          >
            {collapsed ? <ChevronsRight className="size-4 rtl:rotate-180" /> : <ChevronsLeft className="size-4 rtl:rotate-180" />}
          </button>
        </div>
      </nav>

      {/* Mobile bottom bar: ≤ 5 items, icon + label */}
      <nav aria-label="Primary" className="lg:hidden fixed inset-x-0 bottom-0 z-30 border-t border-hairline bg-surface/95 backdrop-blur-sm pb-[env(safe-area-inset-bottom)]">
        <ul className="grid auto-cols-fr grid-flow-col">
          {items.slice(0, 5).map(({ href, key, Icon }) => {
            const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
            return (
              <li key={key}>
                <Link href={href} aria-current={active ? "page" : undefined} className={cn("flex h-14 flex-col items-center justify-center gap-1 text-[0.625rem]", active ? "text-signal" : "text-ink-muted")}>
                  <Icon className="size-5" strokeWidth={1.75} aria-hidden />
                  <span>{t(key)}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </>
  );
}

export function Wordmark({ compact, profile, retail, retailAr, factory, factoryAr }: { compact?: boolean; profile: string; retail: string; retailAr: string; factory: string; factoryAr: string }) {
  const latin = profile === "factory" ? factory : retail;
  const arabic = profile === "factory" ? factoryAr : retailAr;
  return (
    <div className="flex items-baseline gap-2 select-none" aria-label={latin}>
      <span className="display-wide text-[1.0625rem] font-semibold tracking-tight text-ink">{compact ? latin[0] : latin}</span>
      {!compact && <span className="text-[0.9375rem] text-signal" lang="ar" dir="rtl">{arabic}</span>}
    </div>
  );
}
