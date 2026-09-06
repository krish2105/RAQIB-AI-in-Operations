"use client";

import { Background, type Edge, type Node, ReactFlow } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";
import { useTranslations } from "next-intl";
import type { CrewAgent, CrewMessage } from "@/lib/api";
import { useNow } from "@/lib/use-now";

const POS: Record<string, [number, number]> = { FloorOps: [40, 40], ShelfOps: [40, 160], Workforce: [40, 280], Safety: [40, 400], Analyst: [340, 400], Auditor: [340, 220] };

/** Nodes = agents (lit when they ran in the last minute), edges = recent signed messages (animated when < 60 s old). */
export function buildGraph(roster: CrewAgent[], messages: CrewMessage[], now: number): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = roster.map((a) => {
    const lit = !!a.last_run && now - new Date(a.last_run.started).getTime() < 60_000;
    const [x, y] = POS[a.name] ?? [200, 200];
    return {
      id: a.name, position: { x, y }, data: { label: `${a.name}${a.last_run ? ` · ${a.last_run.status}` : ""}` },
      style: { background: lit ? "var(--signal-soft)" : "var(--surface)", color: "var(--ink)", border: `1px solid ${lit ? "var(--signal)" : "var(--hairline-strong)"}`, borderRadius: 10, fontSize: 12, fontFamily: "var(--font-mono)", padding: 8, width: 150 },
    };
  });
  const seen = new Map<string, Edge>();
  for (const m of messages) {
    const key = `${m.from}->${m.to}:${m.schema}`;
    if (seen.has(key)) continue;
    const fresh = now - new Date(m.ts).getTime() < 60_000;
    seen.set(key, { id: key, source: m.from, target: m.to, label: m.schema, animated: fresh, style: { stroke: m.verified ? "var(--signal)" : "var(--critical)" }, labelStyle: { fill: "var(--ink-muted)", fontSize: 10 } });
  }
  return { nodes, edges: [...seen.values()] };
}

export function RunGraph({ roster, messages }: { roster: CrewAgent[]; messages: CrewMessage[] }) {
  const t = useTranslations("crew");
  const now = useNow(5000);
  const { nodes, edges } = useMemo(() => buildGraph(roster, messages, now), [roster, messages, now]);
  return (
    <div className="h-[520px] w-full" data-testid="run-graph" aria-label={t("graph")}>
      <ReactFlow nodes={nodes} edges={edges} fitView proOptions={{ hideAttribution: true }} nodesDraggable={false} nodesConnectable={false} elementsSelectable={false} panOnDrag zoomOnScroll={false}>
        <Background gap={16} color="var(--hairline)" />
      </ReactFlow>
    </div>
  );
}
