import { render, screen } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";
import en from "@/messages/en.json";
import type { AskAnswer } from "@/lib/api";
import { AnswerCard, AnswerText } from "@/components/ask/answer-card";

vi.mock("@/i18n/navigation", () => ({
  Link: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={`/en${href}`} {...rest}>
      {children}
    </a>
  ),
}));

const answer: AskAnswer = {
  q: "Which till had the longest queue last Friday evening?", lang: "en",
  text: "Till 1 had the longest queue on Friday evening with 7 people waiting [c:chunkA]. The SOP allows a third till above ρ 0.85 [c:chunkB].",
  citations: [
    { chunk_id: "chunkA", kind: "event", ts: "2026-09-04T18:47:00Z", event_id: "01EVENTA", clip_url: "/clips/01EVENTA", doc_id: null, doc_title: null, span: "", event_kind: "queue_over", severity: 2 },
    { chunk_id: "chunkB", kind: "document", ts: "2026-09-06T05:45:00Z", event_id: null, clip_url: null, doc_id: "01DOCB", doc_title: "Retail checkout SOP", span: "1. Opening a third till", event_kind: null, severity: null },
  ],
  confidence: 0.8, followups: ["Biggest queue this week", "Show shelf gaps", "When to close a till?"],
  plan: { q: "", lang: "en", mode: "structured", target: "events", kind: "queue_over", time_label: "last friday evening", superlative: "max", source: "model", legs: ["structured", "vector"] },
  provider: "ollama", model: "qwen3:8b", tokens_in: 700, tokens_out: 110, cost_usd: 0, latency_ms: 9300, hits: 6, path: "model", notes: [],
};

const wrap = (ui: React.ReactNode) => render(<NextIntlClientProvider locale="en" messages={en}>{ui}</NextIntlClientProvider>);

describe("AnswerCard", () => {
  it("renders one chip per citation; event chips link to /events/[id], document chips to the viewer at the span", () => {
    wrap(<AnswerCard answer={answer} onFollowUp={() => {}} />);
    const chips = screen.getAllByTestId("citation");
    expect(chips).toHaveLength(2);
    expect(chips[0]).toHaveAttribute("href", "/en/events/01EVENTA");
    expect(chips[1]).toHaveAttribute("href", "/en/documents/01DOCB?chunk=chunkB");
    expect(screen.getAllByTestId("cite-ref").map((s) => s.textContent)).toEqual(["[1]", "[2]"]);
    expect(screen.getByText("Model answer")).toBeInTheDocument();
    expect(screen.getAllByRole("button").map((b) => b.textContent)).toEqual(expect.arrayContaining(["Biggest queue this week"]));
  });
  it("marks unknown citation ids instead of hiding them", () => {
    wrap(<AnswerText text="Fact [c:nope]." citations={[]} />);
    expect(screen.getByTestId("cite-ref").textContent).toBe("[?]");
  });
});
