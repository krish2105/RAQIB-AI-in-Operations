"use client";

/**
 * R3F floor plan. Zones are low extruded slabs on a grid; cameras are small
 * wedges; events pulse as expanding rings at the zone centre and fade over 3 s.
 * Orthographic isometric camera, no post-processing, `frameloop="demand"`
 * except while pulses are alive. Colours come from CSS variables so theme and
 * profile switches repaint the scene.
 */

import { Grid, Html, OrthographicCamera } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useReducedMotion } from "motion/react";
import { useTheme } from "next-themes";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import type { ApiEvent, ApiSite } from "@/lib/api";
import type { Pulse } from "./use-floor-events";

type Floor = ApiSite["floor"];

function readColors() {
  const cs = getComputedStyle(document.documentElement);
  const v = (n: string) => cs.getPropertyValue(n).trim() || "#888";
  return {
    signal: v("--signal"),
    warn: v("--warn"),
    critical: v("--critical"),
    info: v("--info"),
    faint: v("--ink-faint"),
    ink: v("--ink"),
    hair: v("--hairline-strong"),
    ground: v("--ground"),
    surface: v("--surface"),
  };
}
type Colors = ReturnType<typeof readColors>;

const kindColor = (c: Colors, kind: string) =>
  ({ entrance: c.faint, queue: c.warn, checkout: c.signal, shelf: c.info, work_area: c.faint, exclusion: c.critical, machine: c.signal })[kind] ?? c.faint;
const sevColor = (c: Colors, s: number) => (s === 3 ? c.critical : s === 2 ? c.warn : c.info);

export function FloorScene({ floor, lastByZone, pulses, profile }: { floor: Floor; lastByZone: Record<string, ApiEvent>; pulses: Pulse[]; profile: string }) {
  const { resolvedTheme } = useTheme();
  const [colors, setColors] = useState<Colors | null>(null);
  useEffect(() => {
    // read after the theme/profile attribute has been applied
    const id = requestAnimationFrame(() => setColors(readColors()));
    return () => cancelAnimationFrame(id);
  }, [resolvedTheme, profile]);
  if (!colors) return null;
  const W = floor.width_m || 24;
  const D = floor.depth_m || 16;
  return (
    <Canvas dpr={[1, 1.5]} frameloop="demand" gl={{ antialias: true, alpha: true, powerPreference: "low-power" }} style={{ background: "transparent" }}>
      <FitCamera w={W} d={D} />
      <ambientLight intensity={1.1} />
      <directionalLight position={[10, 20, 10]} intensity={0.9} />
      <group position={[-W / 2, 0, -D / 2]}>
        <Grid args={[W, D]} position={[W / 2, 0, D / 2]} cellSize={1} cellThickness={0.5} cellColor={colors.hair} sectionSize={4} sectionThickness={1} sectionColor={colors.hair} fadeDistance={200} infiniteGrid={false} />
        {floor.zones.map((z) => (
          <ZoneSlab key={z.name} zone={z} depthM={D} color={kindColor(colors, z.kind)} last={lastByZone[z.name]} colors={colors} />
        ))}
        {(floor.cameras ?? []).map((c) => (
          <CameraWedge key={c.name} x={c.x} y={D - c.y} z={c.z} yaw={c.yaw} color={colors.ink} />
        ))}
        <Pulses pulses={pulses} floor={floor} colors={colors} />
      </group>
    </Canvas>
  );
}

/** Declarative camera: zoom derived from the canvas size, no imperative mutation. */
function FitCamera({ w, d }: { w: number; d: number }) {
  const size = useThree((s) => s.size);
  const span = Math.max(w * 1.25, d * 1.9);
  const zoom = Math.min(size.width, size.height * 1.6) / span;
  return (
    <OrthographicCamera
      makeDefault
      position={[w * 0.9, Math.max(w, d) * 1.1, d * 1.35]}
      zoom={zoom}
      near={0.1}
      far={500}
      onUpdate={(c) => {
        c.lookAt(0, 0, 0);
        c.updateProjectionMatrix();
      }}
    />
  );
}

function ZoneSlab({ zone, depthM, color, last, colors }: { zone: Floor["zones"][number]; depthM: number; color: string; last?: ApiEvent; colors: Colors }) {
  const t = useTranslations("floor");
  const tk = useTranslations("kind");
  const [hover, setHover] = useState(false);
  const invalidate = useThree((s) => s.invalidate);
  const h = zone.kind === "shelf" || zone.kind === "machine" ? 1.6 : 0.18;
  const cx = zone.x + zone.w / 2;
  const cz = depthM - zone.y - zone.d / 2;
  const edges = useMemo(() => new THREE.EdgesGeometry(new THREE.BoxGeometry(zone.w, h, zone.d)), [zone.w, zone.d, h]);
  return (
    <group position={[cx, h / 2, cz]}>
      <mesh
        onPointerOver={(e) => {
          e.stopPropagation();
          setHover(true);
          invalidate();
        }}
        onPointerOut={() => {
          setHover(false);
          invalidate();
        }}
      >
        <boxGeometry args={[zone.w, h, zone.d]} />
        <meshStandardMaterial color={color} transparent opacity={hover ? 0.6 : 0.35} roughness={0.9} />
      </mesh>
      <lineSegments position={[0, 0.001, 0]} geometry={edges}>
        <lineBasicMaterial color={color} transparent opacity={0.9} />
      </lineSegments>
      <Html position={[-zone.w / 2 + 0.15, h / 2 + 0.05, -zone.d / 2 + 0.15]} transform={false} zIndexRange={[5, 0]} style={{ pointerEvents: "none" }}>
        <span className="whitespace-nowrap font-mono text-[10px] text-ink-muted">{zone.name}</span>
      </Html>
      {hover && (
        <Html position={[0, h + 0.4, 0]} center zIndexRange={[20, 10]} style={{ pointerEvents: "none" }}>
          <div className="w-max max-w-[220px] rounded-md border border-hairline bg-surface px-2.5 py-1.5 text-[11px] shadow-lg">
            <div className="eyebrow mb-1">{t("lastEvent")}</div>
            {last ? (
              <div className="flex items-center gap-2">
                <span aria-hidden className="inline-block size-1.5 rounded-full" style={{ background: sevColor(colors, last.severity) }} />
                <span className="text-ink">{tk(last.kind)}</span>
                <span className="font-mono text-ink-muted">{new Date(last.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</span>
              </div>
            ) : (
              <span className="text-ink-muted">{t("noEvent")}</span>
            )}
          </div>
        </Html>
      )}
    </group>
  );
}

function CameraWedge({ x, y, z, yaw, color }: { x: number; y: number; z: number; yaw: number; color: string }) {
  return (
    <group position={[x, z, y]} rotation={[0, THREE.MathUtils.degToRad(yaw), 0]}>
      <mesh>
        <coneGeometry args={[0.35, 0.9, 4]} />
        <meshStandardMaterial color={color} transparent opacity={0.7} />
      </mesh>
      <mesh position={[0, -z / 2, 0]}>
        <cylinderGeometry args={[0.03, 0.03, z, 6]} />
        <meshBasicMaterial color={color} transparent opacity={0.3} />
      </mesh>
    </group>
  );
}

const PULSE_MS = 3000;

function Pulses({ pulses, floor, colors }: { pulses: Pulse[]; floor: Floor; colors: Colors }) {
  const reduce = useReducedMotion();
  const D = floor.depth_m || 16;
  const zoneCenter = useMemo(() => {
    const m: Record<string, [number, number]> = {};
    for (const z of floor.zones) m[z.name] = [z.x + z.w / 2, D - z.y - z.d / 2];
    return m;
  }, [floor.zones, D]);
  const rings = useRef<Array<{ mesh: THREE.Mesh | null; at: number }>>([]);
  const { invalidate } = useThree();
  const alive = pulses.filter((p) => zoneCenter[p.zone]);
  useEffect(() => {
    invalidate();
  }, [alive.length, invalidate]);
  useFrame(() => {
    if (reduce) return;
    const now = Date.now();
    let any = false;
    rings.current.forEach((r) => {
      if (!r.mesh) return;
      const age = (now - r.at) / PULSE_MS;
      if (age >= 1) {
        r.mesh.visible = false;
        return;
      }
      any = true;
      r.mesh.visible = true;
      const s = 0.6 + age * 2.6;
      r.mesh.scale.set(s, s, s);
      (r.mesh.material as THREE.MeshBasicMaterial).opacity = (1 - age) * 0.85;
    });
    if (any) invalidate();
  });
  return (
    <>
      {alive.slice(0, 24).map((p, i) => {
        const [x, z] = zoneCenter[p.zone];
        return (
          <mesh
            key={p.id}
            ref={(m) => {
              rings.current[i] = { mesh: m, at: p.at };
            }}
            position={[x, 0.12, z]}
            rotation={[-Math.PI / 2, 0, 0]}
          >
            <ringGeometry args={[0.7, 0.85, 48]} />
            <meshBasicMaterial color={sevColor(colors, p.severity)} transparent opacity={reduce ? 0.6 : 0.85} side={THREE.DoubleSide} />
          </mesh>
        );
      })}
    </>
  );
}
