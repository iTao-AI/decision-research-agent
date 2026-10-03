import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useLiveRun } from "./useLiveRun";
import { findingsResponse, markdownResult, structuredRun } from "./test/researchFindingsFixture";

afterEach(() => vi.unstubAllGlobals());
const BASE = "http://127.0.0.1:8000";
const health = { status: "ok", service: "decision-research-agent" };
function response(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status }); }
function setup(handler: (url: string, init?: RequestInit) => Promise<Response>) {
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => handler(String(input), init)));
  return renderHook(() => useLiveRun({ randomUUID: () => "fixed", pollIntervalMs: 1, waitTimeoutMs: 1000 }));
}
type Hook = ReturnType<typeof setup>["result"];
async function ready(result: Hook) {
  act(() => result.current.setMode("live"));
  await act(() => result.current.checkHealth());
}

describe("structured live observation", () => {
  it("uses the observed attached profile despite the generic form selection and retains Markdown", async () => {
    const urls: string[] = [];
    const { result } = setup(async (url) => {
      urls.push(url);
      return response(url.endsWith("/health") ? health : url.endsWith("/findings") ? findingsResponse() : url.endsWith("/result") ? markdownResult() : structuredRun());
    });
    await ready(result);
    await act(() => result.current.attachKnownRun("run_structured"));
    expect(result.current.state.findings?.report.questions).toHaveLength(2);
    expect(result.current.state.result?.artifact.content).toBe("# Canonical report");
    expect(urls).toContain(`${BASE}/api/runs/run_structured/findings`);
    expect(result.current.state.status).toBe("result");
  });

  it("retains exact structured query/scope/profile and key through ambiguous create retry", async () => {
    const bodies: unknown[] = [], keys: string[] = [];
    let posts = 0;
    const { result } = setup(async (url, init) => {
      if (init?.method === "POST") {
        bodies.push(JSON.parse(String(init.body))); keys.push(new Headers(init.headers).get("Idempotency-Key")!);
        if (++posts === 1) throw new TypeError("lost response");
        return response({ run_id: "run_structured", segment_id: "segment", status: "started", thread_id: "demo-console-fixed", idempotent_replay: true });
      }
      return response(url.endsWith("/health") ? health : url.endsWith("/findings") ? findingsResponse() : url.endsWith("/result") ? markdownResult() : structuredRun());
    });
    await ready(result);
    act(() => result.current.setProfile("generic-evidence-report"));
    await act(() => result.current.startNewRun("  原始问题\n😀  "));
    expect(result.current.state.status).toBe("reconciliation_required");
    await act(() => result.current.retryCreate());
    expect(bodies).toEqual([{
      query: "  原始问题\n😀  ", thread_id: "demo-console-fixed", profile_id: "generic-evidence-report",
      scope: { questions: [{ question_id: "q1", text: "  原始问题\n😀  " }] }
    }, bodies[0]]);
    expect(keys).toEqual(["run-create-console-fixed", "run-create-console-fixed"]);
    expect(result.current.state.status).toBe("result");
  });

  it("never requests findings for an observed legacy profile or a blocked delivery", async () => {
    const urls: string[] = [];
    const { result } = setup(async (url) => {
      urls.push(url);
      return response(url.endsWith("/health") ? health : url.endsWith("/result") ? markdownResult("legacy") :
        url.endsWith("/legacy") ? { ...structuredRun("legacy"), profile_id: "generic" } :
        { ...structuredRun("blocked", "blocked"), findings_issues: ["source_not_observed"] });
    });
    await ready(result);
    act(() => result.current.setProfile("generic-evidence-report"));
    await act(() => result.current.attachKnownRun("legacy"));
    expect(result.current.state.result?.run_id).toBe("legacy");
    expect(result.current.state.findings).toBeUndefined();
    await act(() => result.current.attachKnownRun("blocked"));
    expect(result.current.state.run?.findingsIssues).toEqual(["source_not_observed"]);
    expect(result.current.state.status).toBe("terminal");
    expect(result.current.state.result).toBeUndefined();
    expect(urls.some((url) => url.endsWith("/findings"))).toBe(false);
  });

  it.each(["malformed", "unavailable", "transport"])("clears both readers on a %s findings failure after a prior result", async (kind) => {
    let reads = 0;
    const { result } = setup(async (url) => {
      if (url.endsWith("/findings") && ++reads > 1) {
        if (kind === "transport") throw new TypeError("private failure");
        if (kind === "unavailable") return response({ code: "run_result_unavailable", problem: "Unavailable", cause: "Unavailable", fix: "Inspect state", retryable: false }, 409);
        return response({ report: "malformed" });
      }
      return response(url.endsWith("/health") ? health : url.endsWith("/findings") ? findingsResponse() : url.endsWith("/result") ? markdownResult() : structuredRun());
    });
    await ready(result);
    await act(() => result.current.attachKnownRun("run_structured"));
    expect(result.current.state.findings).toBeDefined();
    await act(() => result.current.resumeObservation());
    expect(result.current.state.findings).toBeUndefined();
    expect(result.current.state.result).toBeUndefined();
    expect(result.current.state.error?.code).toBe(kind === "malformed" ? "invalid_response" : kind === "transport" ? "connection_failed" : "run_result_unavailable");
  });

  it.each(["profile", "base", "mode"])("aborts pending findings and ignores late content on %s switch", async (reset) => {
    let release!: (value: Response) => void;
    let signal: AbortSignal | null | undefined;
    const { result } = setup(async (url, init) => {
      if (url.endsWith("/findings")) {
        signal = init?.signal;
        return new Promise<Response>((resolve) => { release = resolve; });
      }
      return response(url.endsWith("/health") ? health : url.endsWith("/result") ? markdownResult() : structuredRun());
    });
    await ready(result);
    let pending!: Promise<void>;
    act(() => { pending = result.current.attachKnownRun("run_structured"); });
    await waitFor(() => expect(signal).toBeDefined());
    act(() => {
      if (reset === "profile") result.current.setProfile("generic-evidence-report");
      else if (reset === "base") result.current.setBaseUrl("http://127.0.0.1:9000");
      else result.current.setMode("static");
    });
    expect(signal?.aborted).toBe(true);
    release(response(findingsResponse()));
    await act(() => pending);
    expect(result.current.state.findings).toBeUndefined();
    expect(result.current.state.result).toBeUndefined();
    expect(result.current.state.run).toBeUndefined();
  });
});
