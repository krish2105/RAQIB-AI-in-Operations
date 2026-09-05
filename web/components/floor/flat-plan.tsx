"use client";

import { useTranslations } from "next-intl";
import type { ApiEvent, ApiSite } from "@/lib/api";
import { ZONE_COLOR } from "./floor-panel";

/** SVG fallback when WebGL is unavailable. Same data, same colours. */
export function FlatPlan({ floor, lastByZone }: { floor: ApiSite["floor"]; lastByZone: Record<string, ApiEvent> }) {
  const tk = useTranslations("kind");
  const W = floor.width_m || 24;
  const D = floor.depth_m || 16;
  return (
    <svg viewBox={`0 0 ${W} ${D}`} className="grid-paper h-full w-full" role="img" aria-label="Floor plan">
      {floor.zones.map((z) => {
        const last = lastByZone[z.name];
        return (
          <g key={z.name}>
            <rect x={z.x} y={D - z.y - z.d} width={z.w} height={z.d} fill={ZONE_COLOR[z.kind] ?? "var(--ink-faint)"} fillOpacity={0.18} stroke={ZONE_COLOR[z.kind] ?? "var(--ink-faint)"} strokeWidth={0.06} />
            <text x={z.x + 0.2} y={D - z.y - z.d + 0.6} fontSize={0.55} fill="var(--ink-muted)" fontFamily="var(--font-mono)">
              {z.name}
            </text>
            {last && (
              <text x={z.x + 0.2} y={D - z.y - z.d + 1.3} fontSize={0.45} fill={last.severity === 3 ? "var(--critical)" : last.severity === 2 ? "var(--warn)" : "var(--info)"} fontFamily="var(--font-mono)">
                {tk(last.kind)}
              </text>
            )}
          </g>
        );
      })}
      {(floor.cameras ?? []).map((c) => (
        <g key={c.name} transform={`translate(${c.x} ${D - c.y}) rotate(${-c.yaw})`}>
          <path d="M0 0 L2.4 -0.9 L2.4 0.9 Z" fill="var(--ink)" fillOpacity={0.12} />
          <circle r={0.22} fill="var(--ink)" />
        </g>
      ))}
    </svg>
  );
}
