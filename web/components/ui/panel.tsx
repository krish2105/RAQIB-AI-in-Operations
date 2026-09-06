"use client";

import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";

interface PanelProps {
  eyebrow?: string;
  title?: string;
  sub?: string;
  actions?: React.ReactNode;
  className?: string;
  bodyClassName?: string;
  children: React.ReactNode;
  as?: "section" | "div" | "article";
}

export function Panel({ eyebrow, title, sub, actions, className, bodyClassName, children, as: Tag = "section" }: PanelProps) {
  return (
    <Tag className={cn("panel flex min-w-0 flex-col overflow-hidden", className)}>
      {(title || eyebrow || actions) && (
        <header className="flex items-start justify-between gap-3 border-b border-hairline px-4 py-3">
          <div className="min-w-0">
            {eyebrow && <div className="eyebrow mb-1">{eyebrow}</div>}
            {title && <h2 className="truncate text-[0.9375rem] font-medium leading-tight text-ink">{title}</h2>}
            {sub && <p className="mt-0.5 text-xs leading-snug text-ink-muted">{sub}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cn("min-h-0 flex-1", bodyClassName)}>{children}</div>
    </Tag>
  );
}

export function Skeleton({ className, style }: { className?: string; style?: React.CSSProperties }) {
  return <div aria-hidden style={style} className={cn("animate-pulse rounded-md bg-raised", className)} />;
}

export function EmptyState({ title, hint, icon, action }: { title: string; hint?: string; icon?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex h-full min-h-[140px] flex-col items-center justify-center gap-2 px-6 py-8 text-center">
      {icon && <div className="text-ink-faint">{icon}</div>}
      <p className="text-sm font-medium text-ink">{title}</p>
      {hint && <p className="max-w-sm text-xs leading-relaxed text-ink-muted">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorState({ what, onRetry }: { what: string; onRetry?: () => void }) {
  const t = useTranslations("dashboard");
  return (
    <div role="alert" className="flex h-full min-h-[140px] flex-col items-center justify-center gap-2 px-6 py-8 text-center">
      <p className="text-sm font-medium text-critical">{t("error", { what })}</p>
      {onRetry && (
        <button onClick={onRetry} className="btn-ghost mt-1">
          {t("retry")}
        </button>
      )}
    </div>
  );
}

export function SevChip({ level, label }: { level: number; label?: string }) {
  const cls = level >= 3 ? "sev-3" : level === 2 ? "sev-2" : "sev-1";
  return (
    <span className={cn("sev", cls)}>
      <span aria-hidden className="inline-block size-1.5 rounded-full bg-current" />
      {label ?? `S${level}`}
    </span>
  );
}

export function Chip({ children, tone = "neutral", className, ...rest }: { children: React.ReactNode; tone?: "neutral" | "signal" | "ok" | "warn" | "critical"; className?: string } & React.HTMLAttributes<HTMLSpanElement>) {
  const tones = {
    neutral: "bg-raised text-ink-muted border-hairline",
    signal: "bg-signal-soft text-signal border-signal/30",
    ok: "bg-[color-mix(in_srgb,var(--ok)_14%,transparent)] text-ok border-ok/30",
    warn: "bg-warn-soft text-warn border-warn/30",
    critical: "bg-critical-soft text-critical border-critical/30",
  };
  return <span className={cn("inline-flex h-[1.375rem] items-center gap-1.5 rounded-full border px-2 font-mono text-[0.6875rem] tracking-wide", tones[tone], className)} {...rest}>{children}</span>;
}
