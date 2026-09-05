"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { useEffect, useState } from "react";
import { useAppStore } from "@/lib/store";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { staleTime: 15_000, refetchOnWindowFocus: false, retry: 1 },
        },
      }),
  );
  return (
    <ThemeProvider attribute="data-theme" defaultTheme="dark" enableSystem={false} storageKey="raqib-theme" disableTransitionOnChange>
      <QueryClientProvider client={client}>
        <ProfileAttribute />
        {children}
      </QueryClientProvider>
    </ThemeProvider>
  );
}

/** Mirrors the active site profile onto <html data-profile> so CSS can swap the signal colour. */
function ProfileAttribute() {
  const profile = useAppStore((s) => s.profile);
  useEffect(() => {
    document.documentElement.setAttribute("data-profile", profile);
  }, [profile]);
  return null;
}
