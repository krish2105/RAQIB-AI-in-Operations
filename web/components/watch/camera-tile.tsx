"use client";

import { VideoOff } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import type { ApiSite, DetectionFrame } from "@/lib/api";
import { api } from "@/lib/api";
import { fmtRelative } from "@/lib/format";
import { useNow } from "@/lib/use-now";
import { cn } from "@/lib/utils";

/** Pixel rect for a normalised box inside a tile of the given size. Exported for tests. */
export function boxRect(box: [number, number, number, number], w: number, h: number) {
  const [x1, y1, x2, y2] = box;
  return { left: x1 * w, top: y1 * h, width: Math.max(1, (x2 - x1) * w), height: Math.max(1, (y2 - y1) * h) };
}

export function CameraTile({ site, camera, zones, frame, streamOn }: { site: string; camera: { name: string; source: string; fps: number }; zones: ApiSite["zones"]; frame?: DetectionFrame; streamOn: boolean }) {
  const t = useTranslations("watch");
  const locale = useLocale();
  const now = useNow(1000);
  const [broken, setBroken] = useState(false);
  const live = !!frame && now - (frame.received ? frame.received * 1000 : new Date(frame.ts).getTime()) < 15_000;
  const camZones = zones.filter((z) => z.camera === camera.name);
  return (
    <figure className="panel-raised relative aspect-video w-full overflow-hidden bg-sunken" data-testid={`camera-${camera.name}`}>
      {streamOn && !broken ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={api.cameraStreamUrl(site, camera.name)} alt="" className="absolute inset-0 size-full object-cover" onError={() => setBroken(true)} />
      ) : (
        <div className="absolute inset-0 flex items-center justify-center text-ink-faint">
          <VideoOff className="size-6" strokeWidth={1.5} aria-hidden />
        </div>
      )}
      {/* zone overlays and detection boxes are drawn from data, never from pixels */}
      <svg className="absolute inset-0 size-full" viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-hidden>
        {camZones.map((z) => (
          <polygon key={z.name} points={z.polygon.map(([x, y]) => `${x * 1000},${y * 1000}`).join(" ")} className={cn("fill-transparent stroke-[3]", z.kind === "exclusion" ? "stroke-critical" : z.kind === "queue" ? "stroke-warn" : "stroke-signal/70")} vectorEffect="non-scaling-stroke" />
        ))}
        {live &&
          frame!.boxes.map((b) => (
            <rect key={b.id} x={b.box[0] * 1000} y={b.box[1] * 1000} width={(b.box[2] - b.box[0]) * 1000} height={(b.box[3] - b.box[1]) * 1000} className="fill-transparent stroke-ink stroke-[2]" vectorEffect="non-scaling-stroke" data-testid="det-box" />
          ))}
      </svg>
      <figcaption className="absolute inset-x-0 bottom-0 flex items-center gap-2 bg-ground/80 px-2 py-1 font-mono text-[0.6875rem] text-ink">
        <span className="font-medium">{camera.name}</span>
        <span className="text-ink-muted">{camera.source} · {camera.fps} fps</span>
        <span className="ms-auto">{live ? t("boxes", { n: frame!.boxes.length }) : frame ? t("lastSeen", { ago: fmtRelative(locale, frame.ts, now) }) : t("noDetections")}</span>
        {!streamOn && <span className="text-ink-faint">{t("streamOff")}</span>}
      </figcaption>
    </figure>
  );
}
