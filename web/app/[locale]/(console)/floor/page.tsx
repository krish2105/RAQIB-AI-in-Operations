import { getTranslations } from "next-intl/server";
import { FloorPanel } from "@/components/floor/floor-panel";
import { Panel } from "@/components/ui/panel";

export async function generateMetadata() {
  const t = await getTranslations("floor");
  return { title: t("title") };
}

export default async function FloorPage() {
  const t = await getTranslations("floor");
  return (
    <Panel eyebrow={t("title")} sub={t("sub")} className="min-h-[60dvh]" bodyClassName="relative">
      <h1 className="sr-only">{t("title")}</h1>
      <FloorPanel full />
    </Panel>
  );
}
