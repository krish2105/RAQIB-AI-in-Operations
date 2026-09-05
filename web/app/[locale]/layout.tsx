import type { Metadata, Viewport } from "next";
import { Archivo, IBM_Plex_Mono, IBM_Plex_Sans, IBM_Plex_Sans_Arabic, IBM_Plex_Sans_Devanagari } from "next/font/google";
import { hasLocale, NextIntlClientProvider } from "next-intl";
import { setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";
import { dirFor, routing } from "@/i18n/routing";
import { Providers } from "@/components/providers";
import "../globals.css";

const plex = IBM_Plex_Sans({ subsets: ["latin", "latin-ext"], variable: "--font-plex", display: "swap", weight: "variable" });
const plexArabic = IBM_Plex_Sans_Arabic({ subsets: ["arabic", "latin"], weight: ["400", "500", "600"], variable: "--font-plex-arabic", display: "swap" });
const plexDevanagari = IBM_Plex_Sans_Devanagari({ subsets: ["devanagari", "latin"], weight: ["400", "500", "600"], variable: "--font-plex-devanagari", display: "swap" });
const plexMono = IBM_Plex_Mono({ subsets: ["latin"], weight: ["400", "500", "600"], variable: "--font-plex-mono", display: "swap" });
const archivo = Archivo({ subsets: ["latin"], variable: "--font-archivo", display: "swap", weight: "variable", axes: ["wdth"] });

export const metadata: Metadata = {
  title: { default: "RAQIB", template: "%s · RAQIB" },
  description: "Vision-driven operations control room for retail floors and factories.",
  applicationName: "RAQIB",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0b0d10" },
    { media: "(prefers-color-scheme: light)", color: "#f4f5f2" },
  ],
};

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  setRequestLocale(locale);
  const fonts = `${plex.variable} ${plexArabic.variable} ${plexDevanagari.variable} ${plexMono.variable} ${archivo.variable}`;
  return (
    <html lang={locale} dir={dirFor(locale)} className={fonts} suppressHydrationWarning>
      <body>
        <NextIntlClientProvider>
          <Providers>{children}</Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
