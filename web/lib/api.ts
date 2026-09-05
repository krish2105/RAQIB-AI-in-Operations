/** Typed client for the RAQIB API. All fetches go through here. */

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export type Severity = 1 | 2 | 3;
export type EventKind =
  | "ppe_violation"
  | "zone_breach"
  | "machine_stopped"
  | "queue_over"
  | "shelf_gap"
  | "footfall_tick"
  | "checkout_served";

export interface ApiEvent {
  id: string;
  site: string;
  camera: string;
  ts: string;
  kind: EventKind;
  severity: Severity;
  payload: Record<string, unknown>;
  clip_path: string | null;
  rule_id: string;
  received_at: string;
  handled: boolean;
  has_clip: boolean;
}

export interface ApiAction {
  id: number;
  site: string;
  event_id: string | null;
  tool: string;
  args: Record<string, unknown>;
  status: "proposed" | "approved" | "rejected" | "executed" | "failed";
  autonomous: boolean;
  reasoning: string;
  confidence: number;
  backend: string;
  result: Record<string, unknown> | null;
  created_at: string;
  decided_at: string | null;
  decided_by: string | null;
}

export interface ApiToolCall {
  id: number;
  site: string;
  action_id: number | null;
  tool: string;
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  ok: boolean;
  error: string | null;
  latency_ms: number;
  cost_usd: number;
  backend: string;
  created_at: string;
}

export interface FloorZone {
  name: string;
  x: number;
  y: number;
  w: number;
  d: number;
  kind: string;
  camera?: string;
}
export interface FloorCamera {
  name: string;
  x: number;
  y: number;
  z: number;
  yaw: number;
}
export interface ApiSite {
  name: string;
  profile: "retail" | "factory";
  tills: number;
  thresholds: Record<string, number>;
  floor: { width_m: number; depth_m: number; zones: FloorZone[]; cameras?: FloorCamera[] };
  machines: Array<Record<string, unknown>>;
  zones: Array<{ name: string; kind: string; camera: string; polygon: number[][]; meta: Record<string, unknown> }>;
  cameras: Array<{ name: string; source: string; fps: number }>;
}

export interface QueueSlot {
  slot_start: string;
  lam_per_h: number;
  mu_per_h: number;
  served: number;
  arrivals: number;
  tills_open: number;
  rho: number;
  wq_model_min: number | null;
  wq_observed_min: number | null;
  queue_observed: number | null;
  mu_source: string;
}

export interface ApiKpis {
  site: string;
  as_of: string;
  profile: "retail" | "factory";
  window_h: number;
  footfall: number;
  footfall_per_hour: number;
  avg_queue: number;
  events_by_severity: Record<string, number>;
  queue_model: QueueSlot[];
  simulated_share: number;
  service_level?: number | null;
  osa?: Record<string, number>;
  osa_store?: number | null;
  time_to_restock_min?: Record<string, number>;
  peak_rho?: number;
  compliance?: number | null;
  downtime_min?: number;
  stopped_machines?: string[];
  breaches?: number;
}

export interface ApiForecast {
  site: string;
  target: string;
  kind: string;
  horizon_h: number;
  sufficient: boolean;
  reason: string;
  history: Array<{ ts: string; value: number }>;
  forecast: Array<{ ts: string; value: number; baseline: number | null }>;
  mae: number | null;
  mape: number | null;
  mae_naive: number | null;
  improvement_pct: number | null;
  peaks: Array<{ ts: string; value: number }>;
  simulated_share: number;
}

export interface ApiWorkforce {
  site: string;
  sufficient: boolean;
  reason?: string;
  day?: string;
  slots?: string[];
  tills?: number[];
  lam?: number[];
  mu?: number;
  rho?: number[];
  wq_min?: Array<number | null>;
  staff_hours?: number;
  baseline_tills?: number;
  baseline_staff_hours?: number;
  savings_hours?: number;
  observed_tills?: number;
}

export interface ApiReport {
  site: string;
  profile: string;
  period: { start: string; end: string };
  generated_at: string;
  lang: string;
  kpis: ApiKpis;
  recommendations: Array<{ title: string; evidence: string; expected_reduction: string }>;
  before_after: { baseline_customer_wait_min: number; with_plan_customer_wait_min: number; reduction_pct: number } | null;
  governance: Record<string, number | null>;
  markdown: string;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { ...init, headers: { "content-type": "application/json", ...(init?.headers || {}) } });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      detail = j.detail || detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

const q = (params: Record<string, string | number | undefined | null>) =>
  "?" +
  Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join("&");

export const api = {
  health: () => request<{ status: string; events: number; agent_backend: string }>("/health"),
  sites: () => request<ApiSite[]>("/sites"),
  site: (name: string) => request<ApiSite>(`/sites/${encodeURIComponent(name)}`),
  events: (p: { site: string; since?: string; until?: string; kind?: string; min_severity?: number; limit?: number }) =>
    request<ApiEvent[]>(`/events${q(p)}`),
  event: (id: string) => request<ApiEvent>(`/events/${id}`),
  clipUrl: (id: string) => `${API_URL}/clips/${id}`,
  kpis: (site: string, window_h = 24) => request<ApiKpis>(`/kpis${q({ site, window_h })}`),
  actions: (p: { site: string; status?: string; tool?: string; limit?: number }) => request<ApiAction[]>(`/actions${q(p)}`),
  actionsForEvent: (site: string, eventId: string) =>
    request<ApiAction[]>(`/actions${q({ site, limit: 500 })}`).then((a) => a.filter((x) => x.event_id === eventId)),
  approve: (id: number, by = "operator", note?: string) =>
    request<ApiAction>(`/actions/${id}/approve`, { method: "POST", body: JSON.stringify({ by, note }) }),
  reject: (id: number, by = "operator", note?: string) =>
    request<ApiAction>(`/actions/${id}/reject`, { method: "POST", body: JSON.stringify({ by, note }) }),
  toolcalls: (site: string, limit = 200) => request<ApiToolCall[]>(`/toolcalls${q({ site, limit })}`),
  toolcallSummary: (site: string) =>
    request<{ total_calls: number; total_cost_usd: number; by_tool: Record<string, { calls: number; ok: number; cost_usd: number; latency_ms_avg: number }> }>(
      `/toolcalls/summary${q({ site })}`,
    ),
  forecast: (site: string, target = "queue", horizon = 24) => request<ApiForecast>(`/forecast${q({ site, target, horizon })}`),
  workforce: (site: string) => request<ApiWorkforce>(`/workforce${q({ site })}`),
  report: (site: string, lang: string) => request<ApiReport>(`/report/weekly${q({ site, lang })}`),
  seed: (site: string, days = 21) => request<{ inserted: number; actions_created: number }>(`/admin/seed${q({ site, days })}`, { method: "POST" }),
  streamUrl: (site: string) => `${API_URL}/stream${q({ site })}`,
};
