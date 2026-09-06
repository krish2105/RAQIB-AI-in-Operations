import { describe, expect, it } from "vitest";
import type { AskAnswer } from "@/lib/api";
import { askReducer, initialAskState, parseFrame } from "@/lib/ask-stream";

const done: AskAnswer = {
  q: "Biggest queue this week", lang: "en", text: "Till 1 had the biggest queue [c:c1].", citations: [], confidence: 0.6, followups: ["a", "b", "c"],
  plan: { q: "", lang: "en", mode: "structured", target: "events", kind: "queue_over", time_label: "this week", superlative: "max", source: "regex", legs: ["structured"] },
  provider: "ollama", model: "qwen3:8b", tokens_in: 1, tokens_out: 1, cost_usd: 0, latency_ms: 10, hits: 3, path: "model", notes: [],
};

describe("ask stream reducer", () => {
  it("renders progressively: plan → hits → deltas append → done replaces with the final text", () => {
    let s = askReducer(initialAskState, { type: "start", q: "Biggest queue this week" });
    expect(s.stage).toBe("planning");
    s = askReducer(s, parseFrame("plan", JSON.stringify(done.plan))!);
    expect(s.stage).toBe("retrieving");
    s = askReducer(s, parseFrame("hits", "[]")!);
    expect(s.stage).toBe("answering");
    s = askReducer(s, parseFrame("delta", JSON.stringify("Till 1 had "))!);
    s = askReducer(s, parseFrame("delta", JSON.stringify("the biggest queue "))!);
    expect(s.text).toBe("Till 1 had the biggest queue ");
    s = askReducer(s, parseFrame("done", JSON.stringify(done))!);
    expect(s.stage).toBe("done");
    expect(s.text).toBe(done.text);
    expect(s.answer?.followups).toHaveLength(3);
  });
  it("turns a malformed frame into an error and can reset", () => {
    const s = askReducer(initialAskState, parseFrame("done", "{not json")!);
    expect(s.stage).toBe("error");
    expect(askReducer(s, { type: "reset" })).toEqual(initialAskState);
    expect(parseFrame("unknown", "{}")).toBeNull();
  });
});
