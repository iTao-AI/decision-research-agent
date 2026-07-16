import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { type LiveStatus, useLiveRun } from "./useLiveRun";

const BASE_URL = "http://127.0.0.1:8000";
const NEXT_BASE_URL = "http://127.0.0.1:9000";
const FIXED_UUID = "11111111-2222-4333-8444-555555555555";

type FetchStep = (
  input: RequestInfo | URL,
  init?: RequestInit
) => Promise<Response>;

type RequestEntry = {
  body?: BodyInit | null;
  headers: Headers;
  method: string;
  url: string;
};

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("useLiveRun", () => {
  it("exports the exact live status contract", () => {
    const statuses = {
      static: true,
      idle: true,
      checking: true,
      ready: true,
      creating: true,
      reconciliation_required: true,
      polling: true,
      observation_interrupted: true,
      terminal: true,
      result: true,
      error: true
    } satisfies Record<LiveStatus, true>;

    expect(Object.keys(statuses)).toEqual([
      "static",
      "idle",
      "checking",
      "ready",
      "creating",
      "reconciliation_required",
      "polling",
      "observation_interrupted",
      "terminal",
      "result",
      "error"
    ]);
  });

  it("moves from ready through creating and polling to the canonical result", async () => {
    const createResponse = deferred<Response>();
    const resultResponse = deferred<Response>();
    const requests = mockFetchSequence([
      jsonResponse({ status: "ok", service: "decision-research-agent" }),
      () => createResponse.promise,
      jsonResponse(runStatus("run_live_001", "completed", "ready")),
      () => resultResponse.promise
    ]);
    const randomUUID = vi.fn(() => FIXED_UUID);
    const { result } = renderHook(() =>
      useLiveRun({ pollIntervalMs: 1, randomUUID, waitTimeoutMs: 500 })
    );
    await makeReady(result);

    let startPromise!: Promise<void>;
    act(() => {
      startPromise = result.current.startNewRun();
    });
    expect(result.current.state.status).toBe("creating");

    createResponse.resolve(jsonResponseValue(createAcknowledgement("run_live_001", false)));
    await waitFor(() => {
      expect(result.current.state.status).toBe("polling");
      expect(result.current.state.run?.run_id).toBe("run_live_001");
    });

    resultResponse.resolve(jsonResponseValue(runResult("run_live_001")));
    await act(async () => {
      await startPromise;
    });

    expect(result.current.state.status).toBe("result");
    expect(result.current.state.created?.idempotent_replay).toBe(false);
    expect(result.current.state.result?.artifact.content).toBe("# Canonical result");
    expect(randomUUID).toHaveBeenCalledTimes(1);
    expect(requests.map(({ method, url }) => [method, url])).toEqual([
      ["GET", `${BASE_URL}/health`],
      ["POST", `${BASE_URL}/api/runs`],
      ["GET", `${BASE_URL}/api/runs/run_live_001`],
      ["GET", `${BASE_URL}/api/runs/run_live_001/result`]
    ]);
  });

  it("rejects a create acknowledgement for a different intent thread", async () => {
    const requests = mockFetchSequence([
      jsonResponse({ status: "ok", service: "decision-research-agent" }),
      jsonResponse({
        ...createAcknowledgement("run_live_wrong_thread", false),
        thread_id: "demo-console-different-thread"
      })
    ]);
    const { result } = renderHook(() =>
      useLiveRun({ pollIntervalMs: 1, randomUUID: () => FIXED_UUID, waitTimeoutMs: 500 })
    );
    await makeReady(result);

    await act(async () => {
      await result.current.startNewRun();
    });

    expect(result.current.state.status).toBe("error");
    expect(result.current.state.error?.code).toBe("invalid_response");
    expect(result.current.state.created).toBeUndefined();
    expect(result.current.state.run).toBeUndefined();
    expect(requests).toHaveLength(2);
  });

  it("rejects a status projection for a different acknowledged run", async () => {
    const requests = mockFetchSequence([
      jsonResponse({ status: "ok", service: "decision-research-agent" }),
      jsonResponse(createAcknowledgement("run_live_expected", false)),
      jsonResponse(
        runStatus(
          "run_live_wrong",
          "failed",
          "failed",
          1,
          "not_required",
          observedFailureCause("execution", "execution_error")
        )
      )
    ]);
    const { result } = renderHook(() =>
      useLiveRun({ pollIntervalMs: 1, randomUUID: () => FIXED_UUID, waitTimeoutMs: 500 })
    );
    await makeReady(result);

    await act(async () => {
      await result.current.startNewRun();
    });

    expect(result.current.state.status).toBe("error");
    expect(result.current.state.error).toMatchObject({
      code: "invalid_response",
      run_id: "run_live_expected"
    });
    expect(result.current.state.created?.run_id).toBe("run_live_expected");
    expect(result.current.state.run).toBeUndefined();
    expect(requests).toHaveLength(3);
  });

  it("rejects a canonical result for a different acknowledged run", async () => {
    const requests = mockFetchSequence([
      jsonResponse({ status: "ok", service: "decision-research-agent" }),
      jsonResponse(createAcknowledgement("run_live_expected", false)),
      jsonResponse(runStatus("run_live_expected", "completed", "ready")),
      jsonResponse(runResult("run_live_wrong"))
    ]);
    const { result } = renderHook(() =>
      useLiveRun({ pollIntervalMs: 1, randomUUID: () => FIXED_UUID, waitTimeoutMs: 500 })
    );
    await makeReady(result);

    await act(async () => {
      await result.current.startNewRun();
    });

    expect(result.current.state.status).toBe("error");
    expect(result.current.state.error).toMatchObject({
      code: "invalid_response",
      run_id: "run_live_expected"
    });
    expect(result.current.state.run?.run_id).toBe("run_live_expected");
    expect(result.current.state.result).toBeUndefined();
    expect(requests).toHaveLength(4);
  });

  it.each([
    {
      label: "status",
      steps: [mismatchedRunError("run_live_other")]
    },
    {
      label: "status with an empty identity",
      steps: [mismatchedRunError("")]
    },
    {
      label: "result",
      steps: [
        jsonResponse(runStatus("run_live_expected", "completed", "ready")),
        mismatchedRunError("run_live_other")
      ]
    }
  ])(
    "fails closed when a known-run $label error names another run",
    async ({ steps }) => {
      const requests = mockFetchSequence([
        jsonResponse({ status: "ok", service: "decision-research-agent" }),
        jsonResponse(createAcknowledgement("run_live_expected", false)),
        ...steps
      ]);
      const { result } = renderHook(() =>
        useLiveRun({ pollIntervalMs: 1, randomUUID: () => FIXED_UUID, waitTimeoutMs: 500 })
      );
      await makeReady(result);

      await act(async () => {
        await result.current.startNewRun();
      });

      expect(result.current.state.status).toBe("error");
      expect(result.current.state.error).toMatchObject({
        code: "invalid_response",
        retryable: false,
        run_id: "run_live_expected"
      });
      expect(JSON.stringify(result.current.state)).not.toContain("run_live_other");
      expect(requests.filter(({ method }) => method === "POST")).toHaveLength(1);
    }
  );

  it("retries an ambiguous create with the same immutable body and key", async () => {
    const requests = mockFetchSequence([
      jsonResponse({ status: "ok", service: "decision-research-agent" }),
      () => Promise.reject(new TypeError("lost create response")),
      jsonResponse(createAcknowledgement("run_live_replayed", true)),
      jsonResponse(runStatus("run_live_replayed", "completed", "ready")),
      jsonResponse(runResult("run_live_replayed"))
    ]);
    const randomUUID = vi.fn(() => FIXED_UUID);
    const { result } = renderHook(() =>
      useLiveRun({ pollIntervalMs: 1, randomUUID, waitTimeoutMs: 500 })
    );
    await makeReady(result);

    await act(async () => {
      await result.current.startNewRun();
    });

    expect(result.current.state.status).toBe("reconciliation_required");
    expect(result.current.state.error?.code).toBe("connection_failed");

    await act(async () => {
      await result.current.retryCreate();
    });

    expect(result.current.state.status).toBe("result");
    expect(result.current.state.created?.idempotent_replay).toBe(true);
    expect(randomUUID).toHaveBeenCalledTimes(1);
    const createRequests = requests.filter(({ method }) => method === "POST");
    expect(createRequests).toHaveLength(2);
    expect(createRequests[1].body).toBe(createRequests[0].body);
    expect(createRequests[1].headers.get("Idempotency-Key")).toBe(
      createRequests[0].headers.get("Idempotency-Key")
    );
    expect(createRequests[0].headers.get("Idempotency-Key")).toBe(
      `run-create-console-${FIXED_UUID}`
    );
  });

  it("retries a create body-read transport failure with the same body and key", async () => {
    const requests = mockFetchSequence([
      jsonResponse({ status: "ok", service: "decision-research-agent" }),
      jsonReadFailure(new TypeError("create response body stream failed")),
      jsonResponse(createAcknowledgement("run_live_body_replayed", true)),
      jsonResponse(runStatus("run_live_body_replayed", "completed", "ready")),
      jsonResponse(runResult("run_live_body_replayed"))
    ]);
    const randomUUID = vi.fn(() => FIXED_UUID);
    const { result } = renderHook(() =>
      useLiveRun({ pollIntervalMs: 1, randomUUID, waitTimeoutMs: 500 })
    );
    await makeReady(result);

    await act(async () => {
      await result.current.startNewRun();
    });

    expect(result.current.state.status).toBe("reconciliation_required");
    expect(result.current.state.error?.code).toBe("connection_failed");

    await act(async () => {
      await result.current.retryCreate();
    });

    expect(result.current.state.status).toBe("result");
    expect(randomUUID).toHaveBeenCalledTimes(1);
    const createRequests = requests.filter(({ method }) => method === "POST");
    expect(createRequests).toHaveLength(2);
    expect(createRequests[1].body).toBe(createRequests[0].body);
    expect(createRequests[1].headers.get("Idempotency-Key")).toBe(
      createRequests[0].headers.get("Idempotency-Key")
    );
  });

  it("discards an ambiguous intent and cannot retry it", async () => {
    const requests = mockFetchSequence([
      jsonResponse({ status: "ok", service: "decision-research-agent" }),
      () => Promise.reject(new TypeError("lost create response"))
    ]);
    const { result } = renderHook(() =>
      useLiveRun({ randomUUID: () => FIXED_UUID, waitTimeoutMs: 500 })
    );
    await makeReady(result);
    await act(async () => {
      await result.current.startNewRun();
    });

    act(() => {
      result.current.discardPendingIntent();
    });

    expect(result.current.state.status).toBe("ready");
    expect(result.current.state.error).toBeUndefined();
    await act(async () => {
      await result.current.retryCreate();
    });
    expect(requests.filter(({ method }) => method === "POST")).toHaveLength(1);
  });

  it("clears the intent after a stable create error", async () => {
    const requests = mockFetchSequence([
      jsonResponse({ status: "ok", service: "decision-research-agent" }),
      jsonResponse(
        {
          code: "run_idempotency_conflict",
          problem: "The key is already bound.",
          cause: "The request differs.",
          fix: "Start a new request.",
          retryable: false
        },
        409
      )
    ]);
    const { result } = renderHook(() =>
      useLiveRun({ randomUUID: () => FIXED_UUID, waitTimeoutMs: 500 })
    );
    await makeReady(result);

    await act(async () => {
      await result.current.startNewRun();
    });

    expect(result.current.state.status).toBe("error");
    expect(result.current.state.error?.code).toBe("run_idempotency_conflict");
    await act(async () => {
      await result.current.retryCreate();
    });
    expect(requests.filter(({ method }) => method === "POST")).toHaveLength(1);
  });

  it("preserves the current projection and resumes a known run with GET only", async () => {
    const requests = mockFetchSequence([
      jsonResponse({ status: "ok", service: "decision-research-agent" }),
      jsonResponse(createAcknowledgement("run_live_resume", false)),
      jsonResponse(runStatus("run_live_resume", "running", "pending", 1)),
      () => Promise.reject(new TypeError("poll connection dropped")),
      jsonResponse(runStatus("run_live_resume", "completed", "ready", 2)),
      jsonResponse(runResult("run_live_resume"))
    ]);
    const { result } = renderHook(() =>
      useLiveRun({ pollIntervalMs: 1, randomUUID: () => FIXED_UUID, waitTimeoutMs: 500 })
    );
    await makeReady(result);

    await act(async () => {
      await result.current.startNewRun();
    });

    expect(result.current.state.status).toBe("observation_interrupted");
    expect(result.current.state.created?.run_id).toBe("run_live_resume");
    expect(result.current.state.run).toMatchObject({
      execution_status: "running",
      run_id: "run_live_resume",
      state_version: 1
    });
    expect(result.current.state.error).toMatchObject({
      code: "connection_failed",
      run_id: "run_live_resume"
    });

    await act(async () => {
      await result.current.retryCreate();
      await result.current.resumeObservation();
    });

    expect(result.current.state.status).toBe("result");
    expect(result.current.state.run?.state_version).toBe(2);
    expect(requests.filter(({ method }) => method === "POST")).toHaveLength(1);
    expect(requests.slice(2).map(({ method }) => method)).toEqual(["GET", "GET", "GET", "GET"]);
    expect(requests.at(-1)?.url).toBe(`${BASE_URL}/api/runs/run_live_resume/result`);
  });

  it("fails closed when a GET-only resume error names another run", async () => {
    const requests = mockFetchSequence([
      jsonResponse({ status: "ok", service: "decision-research-agent" }),
      jsonResponse(createAcknowledgement("run_live_resume_expected", false)),
      jsonResponse(runStatus("run_live_resume_expected", "running", "pending", 1)),
      () => Promise.reject(new TypeError("poll connection dropped")),
      mismatchedRunError("run_live_resume_other")
    ]);
    const { result } = renderHook(() =>
      useLiveRun({ pollIntervalMs: 1, randomUUID: () => FIXED_UUID, waitTimeoutMs: 500 })
    );
    await makeReady(result);

    await act(async () => {
      await result.current.startNewRun();
    });
    expect(result.current.state.status).toBe("observation_interrupted");

    await act(async () => {
      await result.current.resumeObservation();
    });

    expect(result.current.state.status).toBe("error");
    expect(result.current.state.error).toMatchObject({
      code: "invalid_response",
      retryable: false,
      run_id: "run_live_resume_expected"
    });
    expect(JSON.stringify(result.current.state)).not.toContain("run_live_resume_other");
    expect(requests.filter(({ method }) => method === "POST")).toHaveLength(1);
    expect(requests.at(-1)?.method).toBe("GET");
  });

  it.each([
    {
      expectedError: {
        code: "run_status_unavailable",
        problem: "Run status is temporarily unavailable.",
        cause: "The status request was rejected.",
        fix: "Inspect the persisted run status.",
        retryable: false,
        run_id: "run_live_stable_error"
      },
      expectedStateVersion: 1,
      label: "structured status HTTP error",
      steps: () => [
        jsonResponse(runStatus("run_live_stable_error", "running", "pending", 1)),
        jsonResponse(
          {
            code: "run_status_unavailable",
            problem: "Run status is temporarily unavailable.",
            cause: "The status request was rejected.",
            fix: "Inspect the persisted run status.",
            retryable: false
          },
          409
        )
      ]
    },
    {
      expectedError: invalidResponseError(
        "run_live_stable_error",
        "Run projection selected fields were malformed."
      ),
      expectedStateVersion: 1,
      label: "invalid status response",
      steps: () => [
        jsonResponse(runStatus("run_live_stable_error", "running", "pending", 1)),
        jsonResponse({ run_id: "run_live_stable_error" })
      ]
    },
    {
      expectedError: {
        code: "run_result_unavailable",
        problem: "Canonical result is unavailable.",
        cause: "The result request was rejected.",
        fix: "Inspect the canonical result state.",
        retryable: false,
        run_id: "run_live_stable_error"
      },
      expectedStateVersion: 2,
      label: "structured result HTTP error",
      steps: () => [
        jsonResponse(runStatus("run_live_stable_error", "completed", "ready", 2)),
        jsonResponse(
          {
            code: "run_result_unavailable",
            problem: "Canonical result is unavailable.",
            cause: "The result request was rejected.",
            fix: "Inspect the canonical result state.",
            retryable: false
          },
          409
        )
      ]
    },
    {
      expectedError: invalidResponseError(
        "run_live_stable_error",
        "Canonical result selected fields were malformed."
      ),
      expectedStateVersion: 2,
      label: "invalid result response",
      steps: () => [
        jsonResponse(runStatus("run_live_stable_error", "completed", "ready", 2)),
        jsonResponse({ run_id: "run_live_stable_error" })
      ]
    }
  ])(
    "classifies a post-acknowledgement $label as a stable error",
    async ({ expectedError, expectedStateVersion, steps }) => {
      const requests = mockFetchSequence([
        jsonResponse({ status: "ok", service: "decision-research-agent" }),
        jsonResponse(createAcknowledgement("run_live_stable_error", false)),
        ...steps()
      ]);
      const { result } = renderHook(() =>
        useLiveRun({ pollIntervalMs: 1, randomUUID: () => FIXED_UUID, waitTimeoutMs: 500 })
      );
      await makeReady(result);

      await act(async () => {
        await result.current.startNewRun();
      });

      expect(result.current.state.status).toBe("error");
      expect(result.current.state.error).toEqual(expectedError);
      expect(result.current.state.created?.run_id).toBe("run_live_stable_error");
      expect(result.current.state.run?.state_version).toBe(expectedStateVersion);
      expect(requests.filter(({ method }) => method === "POST")).toHaveLength(1);
    }
  );

  it.each([
    {
      expectedError: {
        code: "run_status_unavailable",
        problem: "Run status is temporarily unavailable.",
        cause: "The resumed status request was rejected.",
        fix: "Inspect the persisted run status.",
        retryable: false,
        run_id: "run_live_resume_stable_error"
      },
      label: "structured HTTP error",
      resumeStep: jsonResponse(
        {
          code: "run_status_unavailable",
          problem: "Run status is temporarily unavailable.",
          cause: "The resumed status request was rejected.",
          fix: "Inspect the persisted run status.",
          retryable: false
        },
        409
      )
    },
    {
      expectedError: invalidResponseError(
        "run_live_resume_stable_error",
        "Run projection selected fields were malformed."
      ),
      label: "invalid response",
      resumeStep: jsonResponse({ run_id: "run_live_resume_stable_error" })
    }
  ])("classifies a resumed $label as a stable error", async ({ expectedError, resumeStep }) => {
    const requests = mockFetchSequence([
      jsonResponse({ status: "ok", service: "decision-research-agent" }),
      jsonResponse(createAcknowledgement("run_live_resume_stable_error", false)),
      jsonResponse(runStatus("run_live_resume_stable_error", "running", "pending", 1)),
      () => Promise.reject(new TypeError("poll connection dropped")),
      resumeStep
    ]);
    const { result } = renderHook(() =>
      useLiveRun({ pollIntervalMs: 1, randomUUID: () => FIXED_UUID, waitTimeoutMs: 500 })
    );
    await makeReady(result);
    await act(async () => {
      await result.current.startNewRun();
    });
    expect(result.current.state.status).toBe("observation_interrupted");

    await act(async () => {
      await result.current.resumeObservation();
    });

    expect(result.current.state.status).toBe("error");
    expect(result.current.state.error).toEqual(expectedError);
    expect(result.current.state.run?.state_version).toBe(1);
    expect(requests.filter(({ method }) => method === "POST")).toHaveLength(1);
    expect(requests.at(-1)?.method).toBe("GET");
  });

  it("does not let a deadline race overwrite a stable status HTTP error", async () => {
    vi.useFakeTimers();
    const statusResponse = deferred<Response>();
    const requests = mockFetchSequence([
      jsonResponse({ status: "ok", service: "decision-research-agent" }),
      jsonResponse(createAcknowledgement("run_live_deadline_race", false)),
      () => statusResponse.promise
    ]);
    const { result } = renderHook(() =>
      useLiveRun({ pollIntervalMs: 1, randomUUID: () => FIXED_UUID, waitTimeoutMs: 20 })
    );
    await makeReady(result);

    let startPromise!: Promise<void>;
    act(() => {
      startPromise = result.current.startNewRun();
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(requests).toHaveLength(3);

    act(() => {
      vi.advanceTimersByTime(20);
    });
    statusResponse.resolve(
      jsonResponseValue(
        {
          code: "run_status_unavailable",
          problem: "Run status is temporarily unavailable.",
          cause: "The status request completed at the client deadline.",
          fix: "Inspect the persisted run status.",
          retryable: false
        },
        409
      )
    );
    await act(async () => {
      await startPromise;
    });

    expect(result.current.state.error).toEqual({
      code: "run_status_unavailable",
      problem: "Run status is temporarily unavailable.",
      cause: "The status request completed at the client deadline.",
      fix: "Inspect the persisted run status.",
      retryable: false,
      run_id: "run_live_deadline_race"
    });
    expect(result.current.state.status).toBe("error");
  });

  it("keeps an actual observation deadline classified as interrupted", async () => {
    let statusSignal: AbortSignal | undefined;
    mockFetchSequence([
      jsonResponse({ status: "ok", service: "decision-research-agent" }),
      jsonResponse(createAcknowledgement("run_live_actual_deadline", false)),
      (_input, init) => {
        statusSignal = init?.signal ?? undefined;
        return abortablePending(statusSignal);
      }
    ]);
    const { result } = renderHook(() =>
      useLiveRun({ pollIntervalMs: 1, randomUUID: () => FIXED_UUID, waitTimeoutMs: 20 })
    );
    await makeReady(result);

    await act(async () => {
      await result.current.startNewRun();
    });

    expect(statusSignal?.aborted).toBe(true);
    expect(result.current.state.status).toBe("observation_interrupted");
    expect(result.current.state.error).toMatchObject({
      code: "run_wait_timeout",
      run_id: "run_live_actual_deadline"
    });
  });

  it.each([
    ["review_required", "completed", "required", "review_required", null],
    ["blocked", "completed", "resolved", "blocked", null],
    [
      "execution_error",
      "failed",
      "not_required",
      "failed",
      observedFailureCause("execution", "execution_error")
    ],
    [
      "cancelled",
      "failed",
      "not_required",
      "failed",
      observedFailureCause("execution", "cancelled")
    ],
    [
      "run_timeout",
      "failed",
      "not_required",
      "failed",
      observedFailureCause("execution", "run_timeout")
    ]
  ] as const)(
    "stops at the real %s terminal tuple without requesting a result",
    async (label, executionStatus, reviewStatus, deliveryStatus, failureCause) => {
      const runId = `run_live_terminal_${label}`;
      const requests = mockFetchSequence([
        jsonResponse({ status: "ok", service: "decision-research-agent" }),
        jsonResponse(createAcknowledgement(runId, false)),
        jsonResponse(
          runStatus(runId, executionStatus, deliveryStatus, 1, reviewStatus, failureCause)
        )
      ]);
      const { result } = renderHook(() =>
        useLiveRun({ pollIntervalMs: 1, randomUUID: () => FIXED_UUID, waitTimeoutMs: 500 })
      );
      await makeReady(result);

      await act(async () => {
        await result.current.startNewRun();
      });

      expect(result.current.state.status).toBe("terminal");
      expect(result.current.state.run).toMatchObject({
        delivery_status: deliveryStatus,
        execution_status: executionStatus,
        review_status: reviewStatus,
        run_id: runId
      });
      if (failureCause !== null) {
        expect(result.current.state.run?.failureCause).toMatchObject({
          kind: "observed",
          phase: failureCause.phase,
          code: failureCause.code
        });
      }
      expect(result.current.state.result).toBeUndefined();
      expect(requests.map(({ url }) => url)).toEqual([
        `${BASE_URL}/health`,
        `${BASE_URL}/api/runs`,
        `${BASE_URL}/api/runs/${runId}`
      ]);
    }
  );

  it("aborts and invalidates observation on unmount without issuing a later GET", async () => {
    let observationSignal: AbortSignal | undefined;
    const runId = "run_live_unmount";
    const requests = mockFetchSequence([
      jsonResponse({ status: "ok", service: "decision-research-agent" }),
      jsonResponse(createAcknowledgement(runId, false)),
      (_input, init) => {
        observationSignal = init?.signal ?? undefined;
        return Promise.resolve(
          jsonResponseValue(runStatus(runId, "running", "pending", 1))
        );
      },
      jsonResponse(
        runStatus(
          runId,
          "failed",
          "failed",
          2,
          "not_required",
          observedFailureCause("execution", "execution_error")
        )
      )
    ]);
    const { result, unmount } = renderHook(() =>
      useLiveRun({ pollIntervalMs: 20, randomUUID: () => FIXED_UUID, waitTimeoutMs: 500 })
    );
    await makeReady(result);
    vi.useFakeTimers();

    let startPromise!: Promise<void>;
    act(() => {
      startPromise = result.current.startNewRun();
    });
    await act(async () => {
      for (let iteration = 0; iteration < 10; iteration += 1) {
        await Promise.resolve();
      }
    });
    expect(result.current.state.run?.state_version).toBe(1);
    expect(requests).toHaveLength(3);

    unmount();
    const abortedOnUnmount = observationSignal?.aborted;
    await act(async () => {
      vi.advanceTimersByTime(20);
      await startPromise;
    });

    expect(abortedOnUnmount).toBe(true);
    expect(requests).toHaveLength(3);
  });

  it.each([
    ["mode", "static", "static", BASE_URL],
    ["base URL", "live", "idle", NEXT_BASE_URL]
  ] as const)(
    "aborts a stale create on %s reset without exposing reconciliation",
    async (resetKind, expectedMode, expectedStatus, expectedBaseUrl) => {
      let createSignal: AbortSignal | undefined;
      const requests = mockFetchSequence([
        jsonResponse({ status: "ok", service: "decision-research-agent" }),
        (_input, init) => {
          createSignal = init?.signal ?? undefined;
          return abortablePending(createSignal);
        }
      ]);
      const { result } = renderHook(() =>
        useLiveRun({ randomUUID: () => FIXED_UUID, waitTimeoutMs: 500 })
      );
      await makeReady(result);

      let startPromise!: Promise<void>;
      act(() => {
        startPromise = result.current.startNewRun();
      });
      expect(result.current.state.status).toBe("creating");

      act(() => {
        if (resetKind === "mode") {
          result.current.setMode("static");
        } else {
          result.current.setBaseUrl(NEXT_BASE_URL);
        }
      });
      await act(async () => {
        await startPromise;
      });

      expect(createSignal?.aborted).toBe(true);
      expect(result.current.state).toEqual({
        baseUrl: expectedBaseUrl,
        mode: expectedMode,
        status: expectedStatus
      });
      expect(result.current.state.status).not.toBe("reconciliation_required");
      await act(async () => {
        await result.current.retryCreate();
      });
      expect(requests.filter(({ method }) => method === "POST")).toHaveLength(1);
    }
  );

  it.each([
    ["mode", "static", "static", BASE_URL],
    ["base URL", "live", "idle", NEXT_BASE_URL]
  ] as const)("clears all observed state on %s reset", async (resetKind, mode, status, baseUrl) => {
    mockFetchSequence([
      jsonResponse({ status: "ok", service: "decision-research-agent" }),
      jsonResponse(createAcknowledgement("run_live_reset", false)),
      jsonResponse(runStatus("run_live_reset", "completed", "ready")),
      jsonResponse(runResult("run_live_reset"))
    ]);
    const { result } = renderHook(() =>
      useLiveRun({ pollIntervalMs: 1, randomUUID: () => FIXED_UUID, waitTimeoutMs: 500 })
    );
    await makeReady(result);
    await act(async () => {
      await result.current.startNewRun();
    });
    expect(result.current.state.status).toBe("result");

    act(() => {
      if (resetKind === "mode") {
        result.current.setMode("static");
      } else {
        result.current.setBaseUrl(NEXT_BASE_URL);
      }
    });

    expect(result.current.state).toEqual({ baseUrl, mode, status });
  });
});

async function makeReady(result: ReturnType<typeof renderHook<ReturnType<typeof useLiveRun>, never>>["result"]) {
  act(() => {
    result.current.setMode("live");
  });
  await act(async () => {
    await result.current.checkHealth();
  });
  expect(result.current.state.status).toBe("ready");
}

function mockFetchSequence(steps: FetchStep[]) {
  const requests: RequestEntry[] = [];
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    requests.push({
      body: init?.body,
      headers: new Headers(init?.headers),
      method: init?.method ?? "GET",
      url: String(input)
    });
    const next = steps.shift();
    if (!next) {
      return Promise.reject(new Error("unexpected fetch call"));
    }
    return next(input, init);
  });
  vi.stubGlobal("fetch", fetchMock);
  return requests;
}

function jsonResponse(body: unknown, status = 200): FetchStep {
  return () => Promise.resolve(jsonResponseValue(body, status));
}

function jsonResponseValue(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
    status
  });
}

function jsonReadFailure(error: unknown): FetchStep {
  return () =>
    Promise.resolve({
      json: () => Promise.reject(error),
      ok: true,
      status: 200
    } as Response);
}

function createAcknowledgement(runId: string, idempotentReplay: boolean) {
  return {
    run_id: runId,
    segment_id: `${runId}_seg_000`,
    status: "started",
    thread_id: `demo-console-${FIXED_UUID}`,
    idempotent_replay: idempotentReplay
  };
}

function runStatus(
  runId: string,
  executionStatus: string,
  deliveryStatus: string,
  stateVersion = 1,
  reviewStatus = "not_required",
  failureCause: unknown = null
) {
  return {
    run_id: runId,
    thread_id: `demo-console-${FIXED_UUID}`,
    profile_id: "generic",
    execution_status: executionStatus,
    review_status: reviewStatus,
    delivery_status: deliveryStatus,
    state_version: stateVersion,
    segments: [
      {
        segment_id: `${runId}_seg_000`,
        kind: "initial",
        sequence: 0,
        attempt: 1,
        status: executionStatus
      }
    ],
    evidence: [],
    review_workflow: null,
    review_decision: null,
    review_resolution: null,
    failure_cause: failureCause
  };
}

function observedFailureCause(phase: string, code: string) {
  return {
    schema_version: "dra.run-failure-cause.v1",
    observation_status: "observed",
    phase,
    code,
    recorded_at: "2026-07-16T08:02:00Z"
  };
}

function mismatchedRunError(runId: string): FetchStep {
  return jsonResponse(
    {
      code: "run_status_unavailable",
      problem: "Run observation is unavailable.",
      cause: "The error envelope named another run.",
      fix: "Inspect the requested run only.",
      retryable: false,
      run_id: runId
    },
    409
  );
}

function runResult(runId: string) {
  return {
    run_id: runId,
    execution_status: "completed",
    delivery_status: "ready",
    artifact: {
      artifact_id: "research-report.md",
      kind: "research_report_markdown",
      media_type: "text/markdown",
      content: "# Canonical result",
      content_hash: "sha256:result"
    }
  };
}

function invalidResponseError(runId: string, cause: string) {
  return {
    code: "invalid_response",
    problem: "Backend response could not be rendered safely.",
    cause,
    fix: "Verify the backend version and API contract.",
    retryable: false,
    run_id: runId
  };
}

function abortablePending(signal: AbortSignal | undefined) {
  return new Promise<Response>((_resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    signal?.addEventListener(
      "abort",
      () => reject(new DOMException("Aborted", "AbortError")),
      { once: true }
    );
  });
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
