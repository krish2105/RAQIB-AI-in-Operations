"use client";

import { motion, useReducedMotion } from "motion/react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "ghost" | "danger" | "outline";

export function Button({
  variant = "outline",
  className,
  children,
  busy,
  ...rest
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; busy?: boolean }) {
  const reduce = useReducedMotion();
  const base =
    "inline-flex h-9 min-w-[2.75rem] items-center justify-center gap-2 rounded-md px-3 text-[0.8125rem] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45";
  const styles: Record<Variant, string> = {
    primary: "bg-signal text-signal-ink hover:brightness-110",
    ghost: "text-ink-muted hover:bg-raised hover:text-ink",
    danger: "border border-critical/40 text-critical hover:bg-critical-soft",
    outline: "border border-hairline-strong text-ink hover:bg-raised",
  };
  return (
    <motion.button
      whileTap={reduce || rest.disabled ? undefined : { scale: 0.97 }}
      transition={{ type: "spring", stiffness: 500, damping: 30 }}
      className={cn(base, styles[variant], className)}
      aria-busy={busy || undefined}
      {...(rest as object)}
    >
      {busy && <span aria-hidden className="size-3 animate-spin rounded-full border-2 border-current border-t-transparent" />}
      {children}
    </motion.button>
  );
}
