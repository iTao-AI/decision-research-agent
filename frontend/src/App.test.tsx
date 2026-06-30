import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Decision Research Agent demo console", () => {
  it("renders the six required operator screens in navigation", () => {
    render(<App />);

    const navigation = screen.getByRole("navigation", {
      name: /demo console screens/i
    });

    [
      "Command Center",
      "Run Lifecycle",
      "Evidence Ledger",
      "Review / Verification",
      "Canonical Result",
      "Architecture Explain Mode"
    ].forEach((screenName) => {
      expect(within(navigation).getByRole("button", { name: screenName })).toBeInTheDocument();
    });
  });

  it("defaults to Chinese and can switch to English", async () => {
    const user = userEvent.setup();
    render(<App />);

    expect(screen.getByRole("heading", { name: "研究运行演示控制台" })).toBeInTheDocument();
    expect(screen.getByText("Agent-first / human-governed / Evidence-governed")).toBeInTheDocument();
    expect(screen.getByText("静态快照已启用")).toBeInTheDocument();
    expect(screen.getByText(/Static Demo 和有界 Live Backend consumer/)).toBeInTheDocument();
    expect(screen.queryByText(/只读控制台/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Static fallback plus bounded Live Backend consumer/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "English" }));

    expect(screen.getByRole("heading", { name: "Agent Research Operations Console" })).toBeInTheDocument();
    expect(screen.getByText("Agent-first / human-governed / Evidence-governed")).toBeInTheDocument();
    expect(screen.getByText(/Static fallback plus bounded Live Backend consumer/)).toBeInTheDocument();
    expect(screen.queryByText(/read-only operator console/i)).not.toBeInTheDocument();
  });

  it("states that the UI starts runs without owning authority", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "English" }));
    await user.click(screen.getByRole("button", { name: "Architecture Explain Mode" }));

    expect(screen.getByText(/UI starts runs and consumes public contracts without owning authority/)).toBeInTheDocument();
    expect(screen.queryByText(/only observes public contracts/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/read-only/i)).not.toBeInTheDocument();
  });

  it("does not expose chat input or message bubble as the primary interaction", () => {
    render(<App />);

    expect(screen.queryByPlaceholderText(/message|chat|输入消息|聊天/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /message|chat|输入消息|聊天/i })).not.toBeInTheDocument();
    expect(document.querySelector(".chat-bubble")).not.toBeInTheDocument();
  });

  it("shows static demo data for lifecycle, evidence, review, verification, and result", () => {
    render(<App />);

    expect(screen.getAllByText("run_demo_talent_2026_06_29").length).toBeGreaterThan(0);
    expect(screen.getByText(/evidence_frozen/)).toBeInTheDocument();
    expect(screen.getByText(/ev_001/)).toBeInTheDocument();
    expect(screen.getByText(/claim_candidate_signal/)).toBeInTheDocument();
    expect(screen.getByText("approved")).toBeInTheDocument();
    expect(screen.getByText("verified")).toBeInTheDocument();
    expect(screen.getByText("decision-brief.md")).toBeInTheDocument();
    expect(screen.getByText(/python tools\/decision_research_agent_tool.py run/)).toBeInTheDocument();
  });

  it("keeps Static Demo as the default and exposes a bounded Live Backend mode", () => {
    render(<App />);

    expect(screen.getByRole("button", { name: "静态演示" })).toHaveClass("active");
    expect(screen.getByRole("button", { name: "真实后端" })).toBeInTheDocument();
    expect(screen.getByLabelText("Backend base URL")).toHaveValue("http://127.0.0.1:8000");
    expect(screen.getByText("使用内置静态快照，适合无后端面试演示。")).toBeInTheDocument();
  });

  it("checks backend health and renders bounded live service status", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetchSequence([
      jsonResponse({ status: "ok", service: "decision-research-agent" })
    ]);

    render(<App />);

    await user.click(screen.getByRole("button", { name: "真实后端" }));
    await user.click(screen.getByRole("button", { name: "检查后端" }));

    expect(await screen.findByText("后端可用")).toBeInTheDocument();
    expect(screen.getByText("decision-research-agent")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("http://127.0.0.1:8000/health", expect.any(Object));
  });

  it.each([
    [{ status: "ok", service: "other-service" }, "service_identity_mismatch"],
    [{ status: "degraded", service: "decision-research-agent" }, "backend_not_ready"]
  ])("rejects a non-canonical health response %#", async (health, errorCode) => {
    const user = userEvent.setup();
    mockFetchSequence([jsonResponse(health)]);

    render(<App />);

    await user.click(screen.getByRole("button", { name: "真实后端" }));
    await user.click(screen.getByRole("button", { name: "检查后端" }));

    expect(await screen.findByText(errorCode)).toBeInTheDocument();
    expect(screen.queryByText("后端可用")).not.toBeInTheDocument();
  });

  it.each([
    "https://127.0.0.1:8000",
    "http://localhost:8000",
    "http://127.1:8000",
    "http://127.0.0.1",
    "http://127.0.0.1:8000/path",
    "http://user:secret@127.0.0.1:8000",
    "http://127.0.0.1:8000?token=secret",
    "http://127.0.0.1:8000#fragment"
  ])("rejects out-of-bound backend URL before fetch: %s", async (baseUrl) => {
    const user = userEvent.setup();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await user.click(screen.getByRole("button", { name: "真实后端" }));
    const input = screen.getByLabelText("Backend base URL");
    await user.clear(input);
    await user.type(input, baseUrl);
    await user.click(screen.getByRole("button", { name: "检查后端" }));

    expect(await screen.findByText("invalid_backend_url")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("rejects an empty backend URL before fetch", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    await user.click(screen.getByRole("button", { name: "真实后端" }));
    await user.clear(screen.getByLabelText("Backend base URL"));
    await user.click(screen.getByRole("button", { name: "检查后端" }));

    expect(await screen.findByText("invalid_backend_url")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("runs the live golden path and renders the canonical result", async () => {
    const user = userEvent.setup();
    mockFetchSequence([
      jsonResponse({ status: "ok", service: "decision-research-agent" }),
      jsonResponse({
        status: "started",
        thread_id: "demo-ui-thread",
        run_id: "run_live_001",
        segment_id: "run_live_001_seg_000"
      }),
      jsonResponse({
        run_id: "run_live_001",
        execution_status: "completed",
        delivery_status: "ready"
      }),
      jsonResponse({
        run_id: "run_live_001",
        execution_status: "completed",
        delivery_status: "ready",
        artifact: {
          artifact_id: "research-report.md",
          kind: "research_report_markdown",
          media_type: "text/markdown",
          content: "# Live Result\nSource-backed result from backend.",
          content_hash: "abc123"
        }
      })
    ]);

    render(<App liveOptions={{ pollIntervalMs: 1, waitTimeoutMs: 50 }} />);

    await user.click(screen.getByRole("button", { name: "真实后端" }));
    await user.click(screen.getByRole("button", { name: "检查后端" }));
    await screen.findByText("后端可用");

    await user.click(screen.getByRole("button", { name: "运行并获取结果" }));

    await waitFor(() => {
      expect(screen.getAllByText("run_live_001").length).toBeGreaterThan(0);
    });
    expect(await screen.findByText(/Source-backed result from backend/)).toBeInTheDocument();
    expect(screen.getByText("research-report.md")).toBeInTheDocument();
  });

  it("fetches the canonical result for completed_with_fallback", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetchSequence([
      jsonResponse({ status: "ok", service: "decision-research-agent" }),
      jsonResponse({
        status: "started",
        thread_id: "demo-ui-thread",
        run_id: "run_live_fallback",
        segment_id: "run_live_fallback_seg_000"
      }),
      jsonResponse({
        run_id: "run_live_fallback",
        execution_status: "completed_with_fallback",
        delivery_status: "ready"
      }),
      jsonResponse({
        run_id: "run_live_fallback",
        execution_status: "completed_with_fallback",
        delivery_status: "ready",
        artifact: {
          artifact_id: "research-report.md",
          content: "Fallback result from backend."
        }
      })
    ]);

    render(<App liveOptions={{ pollIntervalMs: 1, waitTimeoutMs: 50 }} />);

    await user.click(screen.getByRole("button", { name: "真实后端" }));
    await user.click(screen.getByRole("button", { name: "检查后端" }));
    await screen.findByText("后端可用");
    await user.click(screen.getByRole("button", { name: "运行并获取结果" }));

    expect(await screen.findByText("Fallback result from backend.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("aborts a hanging poll at the live deadline and preserves the run identity", async () => {
    const user = userEvent.setup();
    let pollSignal: AbortSignal | undefined;
    const fetchMock = mockFetchSequence([
      jsonResponse({ status: "ok", service: "decision-research-agent" }),
      jsonResponse({
        status: "started",
        thread_id: "demo-ui-thread",
        run_id: "run_live_hanging",
        segment_id: "run_live_hanging_seg_000"
      }),
      (_input, init) => {
        pollSignal = init?.signal ?? undefined;
        return new Promise<Response>((_resolve, reject) => {
          pollSignal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
        });
      }
    ]);

    render(<App liveOptions={{ pollIntervalMs: 5, waitTimeoutMs: 20 }} />);

    await user.click(screen.getByRole("button", { name: "真实后端" }));
    await user.click(screen.getByRole("button", { name: "检查后端" }));
    await screen.findByText("后端可用");
    await user.click(screen.getByRole("button", { name: "运行并获取结果" }));

    expect(await screen.findByText("run_wait_timeout")).toBeInTheDocument();
    expect(screen.getAllByText("run_live_hanging").length).toBeGreaterThan(0);
    expect(pollSignal?.aborted).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("does not issue another run GET after sleeping to the deadline", async () => {
    const user = userEvent.setup();
    const fetchMock = mockFetchSequence([
      jsonResponse({ status: "ok", service: "decision-research-agent" }),
      jsonResponse({
        status: "started",
        thread_id: "demo-ui-thread",
        run_id: "run_live_deadline",
        segment_id: "run_live_deadline_seg_000"
      }),
      jsonResponse({
        run_id: "run_live_deadline",
        execution_status: "running",
        delivery_status: "pending"
      })
    ]);

    render(<App liveOptions={{ pollIntervalMs: 20, waitTimeoutMs: 20 }} />);

    await user.click(screen.getByRole("button", { name: "真实后端" }));
    await user.click(screen.getByRole("button", { name: "检查后端" }));
    await screen.findByText("后端可用");
    await user.click(screen.getByRole("button", { name: "运行并获取结果" }));

    expect(await screen.findByText("run_wait_timeout")).toBeInTheDocument();
    expect(screen.getAllByText("run_live_deadline").length).toBeGreaterThan(0);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("normalizes live backend failures without leaking raw exception details", async () => {
    const user = userEvent.setup();
    mockFetchSequence([
      () => Promise.reject(new Error("opaque failure detail"))
    ]);

    render(<App />);

    await user.click(screen.getByRole("button", { name: "真实后端" }));
    await user.click(screen.getByRole("button", { name: "检查后端" }));

    expect(await screen.findByText("connection_failed")).toBeInTheDocument();
    expect(screen.getByText("启动后端或检查 Backend base URL。")).toBeInTheDocument();
    expect(screen.queryByText(/opaque failure detail/)).not.toBeInTheDocument();
  });

  it("restores the deterministic static snapshot after a completed live result", async () => {
    const user = userEvent.setup();
    mockFetchSequence(completedLiveSequence("run_live_static_reset", "Result cleared by static mode."));

    render(<App liveOptions={{ pollIntervalMs: 1, waitTimeoutMs: 50 }} />);

    await user.click(screen.getByRole("button", { name: "真实后端" }));
    await user.click(screen.getByRole("button", { name: "检查后端" }));
    await screen.findByText("后端可用");
    await user.click(screen.getByRole("button", { name: "运行并获取结果" }));
    await screen.findByText("Result cleared by static mode.");

    await user.click(screen.getByRole("button", { name: "静态演示" }));

    expect(screen.queryAllByText("run_live_static_reset")).toHaveLength(0);
    expect(screen.queryByText("Result cleared by static mode.")).not.toBeInTheDocument();
    expect(screen.queryByText("后端可用")).not.toBeInTheDocument();
    expect(screen.getAllByText("run_demo_talent_2026_06_29").length).toBeGreaterThan(0);
    expect(screen.getByText("使用内置静态快照，适合无后端面试演示。")).toBeInTheDocument();
  });

  it("clears connection-scoped state when the backend URL changes", async () => {
    const user = userEvent.setup();
    mockFetchSequence(completedLiveSequence("run_live_url_reset", "Result cleared by URL change."));

    render(<App liveOptions={{ pollIntervalMs: 1, waitTimeoutMs: 50 }} />);

    await user.click(screen.getByRole("button", { name: "真实后端" }));
    await user.click(screen.getByRole("button", { name: "检查后端" }));
    await screen.findByText("后端可用");
    await user.click(screen.getByRole("button", { name: "运行并获取结果" }));
    await screen.findByText("Result cleared by URL change.");

    const input = screen.getByLabelText("Backend base URL");
    await user.clear(input);
    await user.type(input, "http://127.0.0.1:9000");

    expect(screen.queryAllByText("run_live_url_reset")).toHaveLength(0);
    expect(screen.queryByText("Result cleared by URL change.")).not.toBeInTheDocument();
    expect(screen.queryByText("后端可用")).not.toBeInTheDocument();
    expect(screen.getByText("尚未获取 live result。")).toBeInTheDocument();
  });

  it("ignores stale health responses after returning to Static Demo mode", async () => {
    const user = userEvent.setup();
    const health = deferred<Response>();
    let healthSignal: AbortSignal | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
        healthSignal = init?.signal ?? undefined;
        return health.promise;
      })
    );

    render(<App />);

    await user.click(screen.getByRole("button", { name: "真实后端" }));
    await user.click(screen.getByRole("button", { name: "检查后端" }));
    await user.click(screen.getByRole("button", { name: "静态演示" }));

    expect(healthSignal?.aborted).toBe(true);

    await act(async () => {
      health.resolve(
        new Response(JSON.stringify({ status: "ok", service: "decision-research-agent" }), {
          headers: { "Content-Type": "application/json" },
          status: 200
        })
      );
      await health.promise;
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "静态演示" })).toHaveClass("active");
    });
    expect(screen.queryByText("后端可用")).not.toBeInTheDocument();
  });
});

function jsonResponse(body: unknown, status = 200) {
  return () =>
    Promise.resolve(
      new Response(JSON.stringify(body), {
        headers: { "Content-Type": "application/json" },
        status
      })
    );
}

function mockFetchSequence(steps: Array<(input: RequestInfo | URL, init?: RequestInit) => Promise<Response>>) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const next = steps.shift();
    if (!next) {
      return Promise.reject(new Error("unexpected fetch call"));
    }
    return next(input, init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function completedLiveSequence(runId: string, content: string) {
  return [
    jsonResponse({ status: "ok", service: "decision-research-agent" }),
    jsonResponse({
      status: "started",
      thread_id: "demo-ui-thread",
      run_id: runId,
      segment_id: `${runId}_seg_000`
    }),
    jsonResponse({
      run_id: runId,
      execution_status: "completed",
      delivery_status: "ready"
    }),
    jsonResponse({
      run_id: runId,
      execution_status: "completed",
      delivery_status: "ready",
      artifact: {
        artifact_id: "research-report.md",
        content
      }
    })
  ];
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });
  return { promise, reject, resolve };
}
