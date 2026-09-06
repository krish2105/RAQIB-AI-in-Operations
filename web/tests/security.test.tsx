/* eslint-disable @typescript-eslint/no-unused-vars */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { describe, expect, it, vi } from "vitest";
import en from "@/messages/en.json";
import { useAppStore } from "@/lib/store";
import { AsiScorecard } from "@/components/security/asi-scorecard";
import { PolicyEditor, policyDiff } from "@/components/security/policy-editor";

const values = { rho_threshold: 0.85, review_confidence: 0.6, work_order_cooldown_h: 4, vlm_review_confidence: 0.8 };
const state = { role: "admin" as "admin" | "operator" };
const putPolicy = vi.fn(async (_site: string, v: typeof values, _note: string) => ({ site: "s", values: v, diff: { rho_threshold: { before: 0.85, after: 0.9 } }, updated_by: "dev@raqib.local" }));

vi.mock("@/lib/api", async (orig) => {
  const mod = await orig<typeof import("@/lib/api")>();
  return {
    ...mod,
    api: {
      ...mod.api,
      me: vi.fn(async () => ({ id: "u", email: "x@y", role: state.role, site_ids: [], anonymous: false, auth_required: false, capabilities: { read: true, approve: true, policy: state.role === "admin" } })),
      policy: vi.fn(async () => ({ site: "s", values, defaults: values, updated_by: null, updated_at: null, note: null })),
      putPolicy: (...a: Parameters<typeof putPolicy>) => putPolicy(...a),
      securityScorecard: vi.fn(async () => ({ date: "2026-09-06T10:00:00Z", passed: 9, failed: 1, total: 10, source: "s", mapping_doc: "m",
        results: [{ asi: "ASI01", risk: "Goal hijack", control: "c", test: "t", passed: true, evidence: {}, error: null }, { asi: "ASI02", risk: "Tool misuse", control: "c", test: "t", passed: false, evidence: {}, error: "boom" }] })),
    },
  };
});

const wrap = (ui: React.ReactNode) => render(<QueryClientProvider client={new QueryClient()}><NextIntlClientProvider locale="en" messages={en}>{ui}</NextIntlClientProvider></QueryClientProvider>);

describe("Security", () => {
  it("policyDiff lists only the changed keys", () => {
    expect(policyDiff(values, values)).toEqual({});
    expect(policyDiff(values, { ...values, rho_threshold: 0.9 })).toEqual({ rho_threshold: { before: 0.85, after: 0.9 } });
  });
  it("admin edits the till threshold, reviews the diff, confirms with a note", async () => {
    useAppStore.setState({ site: "s" });
    state.role = "admin";
    wrap(<PolicyEditor />);
    const input = await screen.findByTestId("policy-rho_threshold");
    expect(screen.getByTestId("policy-review")).toBeDisabled();
    fireEvent.change(input, { target: { value: "0.9" } });
    fireEvent.click(screen.getByTestId("policy-review"));
    expect(screen.getByTestId("diff-rho_threshold")).toHaveTextContent("0.85");
    expect(screen.getByTestId("diff-rho_threshold")).toHaveTextContent("0.9");
    fireEvent.change(screen.getByTestId("policy-note"), { target: { value: "peak season" } });
    fireEvent.click(screen.getByTestId("policy-confirm"));
    await waitFor(() => expect(putPolicy).toHaveBeenCalledWith("s", { ...values, rho_threshold: 0.9 }, "peak season"));
    expect(await screen.findByTestId("policy-saved")).toHaveTextContent("dev@raqib.local");
  });
  it("operator sees the editor read-only with no review button", async () => {
    useAppStore.setState({ site: "s" });
    state.role = "operator";
    wrap(<PolicyEditor />);
    const input = await screen.findByTestId("policy-rho_threshold");
    await waitFor(() => expect(input).toBeDisabled());
    expect(screen.getByTestId("policy-readonly")).toBeInTheDocument();
    expect(screen.queryByTestId("policy-review")).toBeNull();
  });
  it("scorecard shows pass and fail cells with the summary", async () => {
    wrap(<AsiScorecard />);
    expect(await screen.findByTestId("asi-summary")).toHaveTextContent("9 of 10 passed");
    expect(screen.getByTestId("asi-ASI01")).toHaveAttribute("data-passed", "true");
    expect(screen.getByTestId("asi-ASI02")).toHaveAttribute("data-passed", "false");
    expect(screen.getByText("boom")).toBeInTheDocument();
  });
});
