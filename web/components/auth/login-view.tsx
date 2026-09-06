"use client";

import { LogIn, Mail } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { Link } from "@/i18n/navigation";
import { signInWithEmail, signInWithGoogle, useSession } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Chip, Panel } from "@/components/ui/panel";

export function LoginView() {
  const t = useTranslations("auth");
  const locale = useLocale();
  const { session, enabled } = useSession();
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [err, setErr] = useState<string | null>(null);
  const redirect = typeof window !== "undefined" ? `${window.location.origin}/${locale}` : "/";
  return (
    <div className="mx-auto flex min-h-dvh max-w-md flex-col justify-center gap-4 px-4 py-10">
      <Panel eyebrow="RAQIB" title={t("title")} sub={t("sub")} bodyClassName="flex flex-col gap-3 p-4">
        {!enabled ? (
          <p className="text-sm text-ink-muted" data-testid="auth-off">{t("notConfigured")} <Link href="/" className="text-signal underline">Dashboard</Link></p>
        ) : session ? (
          <div className="flex flex-col gap-2 text-sm text-ink"><span>{t("signedInAs")} <span className="font-mono">{session.user.email}</span></span><Link href="/" className="text-signal underline">Dashboard</Link></div>
        ) : (
          <>
            <form className="flex flex-col gap-2" onSubmit={async (e) => { e.preventDefault(); setState("sending"); const { error } = await signInWithEmail(email, redirect); setErr(error); setState(error ? "error" : "sent"); }}>
              <label className="text-xs text-ink-muted" htmlFor="email">{t("email")}</label>
              <input id="email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="h-10 rounded-md border border-hairline-strong bg-surface px-3 text-ink" data-testid="login-email" />
              <Button type="submit" variant="primary" busy={state === "sending"} disabled={state === "sending"}><Mail className="size-4" /> {state === "sending" ? t("sending") : t("sendLink")}</Button>
              {state === "sent" && <Chip tone="ok">{t("sent")}</Chip>}
              {state === "error" && err && <Chip tone="critical">{err}</Chip>}
            </form>
            <Button variant="outline" onClick={() => signInWithGoogle(redirect)}><LogIn className="size-4" /> {t("google")}</Button>
          </>
        )}
      </Panel>
    </div>
  );
}
