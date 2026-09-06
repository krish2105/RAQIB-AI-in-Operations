"use client";

import { useQuery } from "@tanstack/react-query";
import { LogOut, UserRound } from "lucide-react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { api } from "@/lib/api";
import { signOut, useSession } from "@/lib/auth";

export function UserChip() {
  const t = useTranslations("auth");
  const { session, enabled } = useSession();
  const me = useQuery({ queryKey: ["me", session?.access_token ?? "anon"], queryFn: api.me, retry: false, staleTime: 60_000 });
  if (!enabled) return null;
  if (!session) return <Link href="/login" className="inline-flex h-8 items-center gap-1.5 rounded-md border border-hairline px-2 font-mono text-[0.6875rem] text-ink-muted hover:text-ink"><UserRound className="size-3.5" /> {t("title")}</Link>;
  return (
    <span className="inline-flex h-8 items-center gap-2 rounded-md border border-hairline px-2 font-mono text-[0.6875rem] text-ink-muted" data-testid="user-chip">
      <UserRound className="size-3.5" /> {session.user.email}{me.data ? ` · ${me.data.role}` : ""}
      <button type="button" onClick={() => signOut()} aria-label={t("signOut")} className="text-ink-faint hover:text-critical"><LogOut className="size-3.5" /></button>
    </span>
  );
}
