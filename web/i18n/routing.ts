import { defineRouting } from "next-intl/routing";

export const routing = defineRouting({
  locales: ["en", "hi", "ar"],
  defaultLocale: "en",
  localePrefix: "always",
});

export type Locale = (typeof routing.locales)[number];

export const RTL_LOCALES: readonly Locale[] = ["ar"];

export function dirFor(locale: string): "rtl" | "ltr" {
  return (RTL_LOCALES as readonly string[]).includes(locale) ? "rtl" : "ltr";
}
