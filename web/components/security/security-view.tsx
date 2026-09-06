"use client";

import { useTranslations } from "next-intl";
import { AsiScorecard } from "./asi-scorecard";
import { MemoryGuardLog } from "./memory-guard-log";
import { PolicyEditor } from "./policy-editor";
import { RedTeamRuns } from "./redteam-runs";

export function SecurityView() {
  const t = useTranslations("security");
  return (
    <div className="flex flex-col gap-3">
      <h1 className="sr-only">{t("title")}</h1>
      <AsiScorecard />
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <PolicyEditor />
        <RedTeamRuns />
      </div>
      <MemoryGuardLog />
    </div>
  );
}
