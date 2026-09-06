"use client";

import { useTranslations } from "next-intl";
import { Panel } from "@/components/ui/panel";
import { IntegrationsPanel } from "./integrations-panel";

export function SettingsView() {
  const t = useTranslations("settings");
  return (
    <div className="flex flex-col gap-3">
      <h1 className="sr-only">{t("title")}</h1>
      <Panel eyebrow={t("integrations")} sub={t("sub")}>
        <IntegrationsPanel />
      </Panel>
    </div>
  );
}
