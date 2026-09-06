import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";
import en from "@/messages/en.json";
import type { ApiOpinion, DetectionFrame } from "@/lib/api";
import { CameraTile, boxRect } from "@/components/watch/camera-tile";
import { OpinionRow, verdictOf } from "@/components/watch/opinion-panel";

vi.mock("@/i18n/navigation", () => ({ Link: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a> }));

const wrap = (ui: React.ReactNode) => render(
  <QueryClientProvider client={new QueryClient()}>
    <NextIntlClientProvider locale="en" messages={en}>{ui}</NextIntlClientProvider>
  </QueryClientProvider>,
);
const cam = { name: "cam1", source: "file", fps: 25 };
const zones = [{ name: "queue_till_1", kind: "queue", camera: "cam1", polygon: [[0, 0.2], [0.5, 0.2], [0.5, 1], [0, 1]], meta: {} }];
const frame: DetectionFrame = { site: "s", camera: "cam1", ts: new Date().toISOString(), w: 1920, h: 1080, received: Date.now() / 1000,
  boxes: [{ id: 1, cls: "person", conf: 0.9, box: [0.1, 0.1, 0.3, 0.6] }, { id: 2, cls: "person", conf: 0.8, box: [0.5, 0.2, 0.7, 0.9] }] };

describe("Watch", () => {
  it("maps normalised boxes to pixels", () => {
    expect(boxRect([0.1, 0.2, 0.3, 0.6], 200, 100)).toEqual({ left: 20, top: 20, width: 40, height: 40 });
  });
  it("tile degrades to detections only when the stream is off, still drawing boxes and zones", () => {
    wrap(<CameraTile site="s" camera={cam} zones={zones} frame={frame} streamOn={false} />);
    expect(screen.getAllByTestId("det-box")).toHaveLength(2);
    expect(screen.getByText("Stream off. Showing detections only.")).toBeInTheDocument();
    expect(screen.getByText("2 boxes")).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
    expect(document.querySelector("polygon")).not.toBeNull();
  });
  it("tile shows the proxied stream image when the stream is on", () => {
    wrap(<CameraTile site="s" camera={cam} zones={zones} frame={frame} streamOn />);
    expect(document.querySelector("img")?.getAttribute("src")).toContain("/cameras/s/cam1/stream");
  });
  it("opinion verdicts: agree, disagree with review, unavailable", () => {
    const base: ApiOpinion = { id: 1, event_id: "e", site: "s", rule_severity: 3, agrees: true, confidence: 0.9, observed: "queue", disagreement_reason: null,
      suggested_severity: 1, disagreement: true, review_action_id: null, trigger: "auto_sev3", status: "ok", model: "m", provider: "ollama", frames: 3, tokens: 1, cost_usd: 0, latency_ms: 5, ts: new Date().toISOString() };
    expect(verdictOf(base)).toBe("agrees");
    expect(verdictOf({ ...base, agrees: false })).toBe("disagrees");
    expect(verdictOf({ ...base, status: "no_frames", agrees: null })).toBe("unavailable");
    wrap(<ul><OpinionRow o={{ ...base, agrees: false, disagreement_reason: "empty zone", review_action_id: 7 }} /></ul>);
    expect(screen.getByTestId("opinion")).toHaveAttribute("data-verdict", "disagrees");
    expect(screen.getByText("Review requested")).toBeInTheDocument();
    expect(screen.getByText("rule severity 3")).toBeInTheDocument();  // the recorded severity is always shown unchanged
    expect(screen.getByText("suggested severity 1")).toBeInTheDocument();
  });
});
