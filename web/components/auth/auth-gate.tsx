"use client";

import { useQuery } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api";
import { useSession } from "@/lib/auth";

/** Renders children unless the API says sign-in is required and there is no session. Never blocks the dev/demo mode. */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const t = useTranslations("auth");
  const { session, ready, enabled } = useSession();
  const me = useQuery({ queryKey: ["me", session?.access_token ?? "anon"], queryFn: api.me, enabled: ready, retry: false, staleTime: 60_000 });
  const required = (me.error as { status?: number } | null)?.status === 401 || me.data?.auth_required === true;
  if (ready && required && !session && enabled) {
    return (
      <div className="mx-auto flex min-h-[60dvh] max-w-md flex-col items-center justify-center gap-3 text-center">
        <p className="text-lg font-medium text-ink">{t("required")}</p>
        <p className="text-sm text-ink-muted">{t("requiredSub")}</p>
        <Link href="/login" className="rounded-md bg-signal px-4 py-2 text-sm text-signal-ink">{t("title")}</Link>
      </div>
    );
  }
  return <>{children}</>;
}
