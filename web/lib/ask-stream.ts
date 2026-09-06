/**
 * Ask streaming: the API emits SSE stages (plan → hits → delta* → done). This reducer is pure so the
 * progressive render is testable without a browser; `useAskStream` binds it to an EventSource.
 */
"use client";

import { useCallback, useEffect, useReducer, useRef } from "react";
import { api, type AskAnswer, type AskHit, type AskPlan } from "./api";

export type Stage = "idle" | "planning" | "retrieving" | "answering" | "done" | "error";

export interface AskStreamState {
  stage: Stage;
  q: string;
  plan: AskPlan | null;
  hits: AskHit[];
  text: string;
  answer: AskAnswer | null;
  error: string | null;
}

export const initialAskState: AskStreamState = { stage: "idle", q: "", plan: null, hits: [], text: "", answer: null, error: null };

export type StageEvent =
  | { type: "start"; q: string }
  | { type: "plan"; data: AskPlan }
  | { type: "hits"; data: AskHit[] }
  | { type: "delta"; data: string }
  | { type: "done"; data: AskAnswer }
  | { type: "error"; message: string }
  | { type: "reset" };

export function askReducer(state: AskStreamState, ev: StageEvent): AskStreamState {
  switch (ev.type) {
    case "start":
      return { ...initialAskState, stage: "planning", q: ev.q };
    case "plan":
      return { ...state, stage: "retrieving", plan: ev.data };
    case "hits":
      return { ...state, stage: "answering", hits: ev.data };
    case "delta":
      return { ...state, stage: "answering", text: state.text + ev.data };
    case "done":
      return { ...state, stage: "done", text: ev.data.text, answer: ev.data, plan: ev.data.plan ?? state.plan };
    case "error":
      return { ...state, stage: "error", error: ev.message };
    case "reset":
      return initialAskState;
  }
}

/** Parse one SSE frame ("event: x\ndata: {...}") into a StageEvent. Exported for tests. */
export function parseFrame(event: string, data: string): StageEvent | null {
  try {
    if (event === "plan") return { type: "plan", data: JSON.parse(data) };
    if (event === "hits") return { type: "hits", data: JSON.parse(data) };
    if (event === "delta") return { type: "delta", data: JSON.parse(data) };
    if (event === "done") return { type: "done", data: JSON.parse(data) };
  } catch {
    return { type: "error", message: `bad ${event} frame` };
  }
  return null;
}

export function useAskStream() {
  const [state, dispatch] = useReducer(askReducer, initialAskState);
  const src = useRef<EventSource | null>(null);

  const stop = useCallback(() => {
    src.current?.close();
    src.current = null;
  }, []);

  const ask = useCallback(
    (q: string, site: string, lang: string) => {
      stop();
      dispatch({ type: "start", q });
      const es = new EventSource(api.askStreamUrl({ q, site, lang }));
      src.current = es;
      for (const name of ["plan", "hits", "delta", "done"] as const) {
        es.addEventListener(name, (e) => {
          const ev = parseFrame(name, (e as MessageEvent).data);
          if (ev) dispatch(ev);
          if (name === "done") {
            es.close();
            src.current = null;
          }
        });
      }
      es.onerror = () => {
        es.close();
        src.current = null;
        dispatch({ type: "error", message: "stream" });
      };
    },
    [stop],
  );

  useEffect(() => stop, [stop]);
  return { state, ask, stop, reset: () => dispatch({ type: "reset" }) };
}
