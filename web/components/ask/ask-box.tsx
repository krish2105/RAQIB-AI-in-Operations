"use client";

import { Send, Square } from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";

export function AskBox({ value, onChange, onSubmit, onStop, busy }: { value: string; onChange: (v: string) => void; onSubmit: () => void; onStop: () => void; busy: boolean }) {
  const t = useTranslations("ask");
  const ref = useRef<HTMLTextAreaElement>(null);

  // keyboard-first: "/" focuses the box from anywhere on the page
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (e.key === "/" && tag !== "INPUT" && tag !== "TEXTAREA" && !e.metaKey && !e.ctrlKey) {
        e.preventDefault();
        ref.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <form
      className="panel flex items-end gap-2 p-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (!busy && value.trim()) onSubmit();
      }}
    >
      <label className="sr-only" htmlFor="ask-input">{t("title")}</label>
      <textarea
        id="ask-input"
        ref={ref}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (!busy && value.trim()) onSubmit();
          }
        }}
        rows={1}
        maxLength={500}
        placeholder={t("placeholder")}
        dir="auto"
        className="min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-[0.9375rem] text-ink outline-none placeholder:text-ink-faint"
        data-testid="ask-input"
      />
      <span className="hidden font-mono text-[0.625rem] text-ink-faint sm:inline">{t("shortcut")}</span>
      {busy ? (
        <Button type="button" variant="outline" onClick={onStop} aria-label={t("stop")}>
          <Square className="size-3.5" /> {t("stop")}
        </Button>
      ) : (
        <Button type="submit" variant="primary" disabled={!value.trim()} data-testid="ask-submit">
          <Send className="size-3.5 rtl:-scale-x-100" /> {t("send")}
        </Button>
      )}
    </form>
  );
}
