"use client";

import { useAppStore } from "@/lib/store";
import { cn } from "@/lib/utils";

/** Shifts the page content by the rail width; the rail itself is fixed. */
export function ConsoleFrame({ children }: { children: React.ReactNode }) {
  const collapsed = useAppStore((s) => s.railCollapsed);
  return (
    <div className={cn("flex min-h-dvh flex-col transition-[padding] duration-300 ease-[var(--ease-out-expo)]", collapsed ? "lg:ps-[var(--rail-w-collapsed)]" : "lg:ps-[var(--rail-w)]")}>
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:start-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-signal focus:px-3 focus:py-2 focus:text-signal-ink">
        Skip to content
      </a>
      {children}
    </div>
  );
}
