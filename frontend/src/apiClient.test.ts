import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ClientRequestError,
  createRunIntent,
  getHealth,
  getResult,
  getRun,
  isAmbiguousCreateError,
  startRun,
  type RunCreateIntent
} from "./apiClient";

const BASE_URL = "http://127.0.0.1:8000";
const FIXED_UUID = "11111111-2222-4333-8444-555555555555";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("keyed live run creation", () => {
  it("creates one immutable bounded browser intent", () => {
    const intent = createRunIntent(() => FIXED_UUID);

    expect(intent).toEqual({
      idempotencyKey: `run-create-console-${FIXED_UUID}`,
      payload: {
        query: "Generate a short evidence-bound result for the Agent Research Operations Console.",
        thread_id: `demo-console-${FIXED_UUID}`,
        profile_id: "generic",
        scope: {}
      }
    });
    expect(Object.isFrozen(intent)).toBe(true);
    expect(Object.isFrozen(intent.payload)).toBe(true);
    expect(Object.isFrozen(intent.payload.scope)).toBe(true);
  });

  it("sends the immutable payload with the raw key only in the idempotency header", async () => {
    const intent = createRunIntent(() => FIXED_UUID);
    const fetchMock = stubFetch(
      jsonResponse({
        run_id: "run_live_001",
        segment_id: "run_live_001_seg_000",
        status: "started",
        thread_id: intent.payload.thread_id,
        idempotent_replay: false
      })
    );

    const result = await startRun(BASE_URL, intent);

    expect(result).toEqual({
      run_id: "run_live_001",
      segment_id: "run_live_001_seg_000",
      status: "started",
      thread_id: intent.payload.thread_id,
      idempotent_replay: false
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [input, init] = fetchMock.mock.calls[0];
    const request = {
      body: init?.body,
      headers: [...new Headers(init?.headers).entries()],
      method: init?.method,
      url: String(input)
    };
    expect(request.method).toBe("POST");
    expect(request.url).toBe(`${BASE_URL}/api/runs`);
    expect(request.url).not.toContain(intent.idempotencyKey);
    expect(request.headers).toContainEqual(["idempotency-key", intent.idempotencyKey]);
    expect(JSON.parse(String(request.body))).toEqual(intent.payload);
    expect(String(request.body)).not.toContain(intent.idempotencyKey);
  });

  it("rejects a create acknowledgement for a different thread identity", async () => {
    const intent = createRunIntent(() => FIXED_UUID);
    stubFetch(
      jsonResponse({
        run_id: "run_live_wrong_thread",
        segment_id: "run_live_wrong_thread_seg_000",
        status: "started",
        thread_id: "demo-console-different-thread",
        idempotent_replay: false
      })
    );

    const error = await captureError(startRun(BASE_URL, intent));

    expect(error).toMatchObject({ details: { code: "invalid_response" } });
  });

  it.each([undefined, "false", 0, null])(
    "rejects a non-boolean idempotent_replay value: %s",
    async (idempotentReplay) => {
      const intent = createRunIntent(() => FIXED_UUID);
      stubFetch(
        jsonResponse({
          run_id: "run_live_001",
          segment_id: "run_live_001_seg_000",
          status: "started",
          thread_id: intent.payload.thread_id,
          idempotent_replay: idempotentReplay
        })
      );

      await expect(startRun(BASE_URL, intent)).rejects.toMatchObject({
        details: { code: "invalid_response" }
      });
    }
  );

  it("marks fetch-level connection failures ambiguous without exposing raw errors", async () => {
    const intent = createRunIntent(() => FIXED_UUID);
    stubFetch(Promise.reject(new Error(`opaque failure ${intent.idempotencyKey}`)));

    const error = await captureError(startRun(BASE_URL, intent));

    expect(error).toBeInstanceOf(ClientRequestError);
    expect(isAmbiguousCreateError(error)).toBe(true);
    expect(JSON.stringify((error as ClientRequestError).details)).not.toContain(intent.idempotencyKey);
  });

  it("marks a pre-acknowledgement AbortError ambiguous", () => {
    expect(isAmbiguousCreateError(new DOMException("Aborted", "AbortError"))).toBe(true);
  });

  it.each([
    ["transport failure", new TypeError("response body stream failed")],
    ["abort", new DOMException("Aborted", "AbortError")]
  ])("marks a create response body-read %s ambiguous", async (_label, bodyError) => {
    const intent = createRunIntent(() => FIXED_UUID);
    stubFetch(jsonReadFailureResponse(bodyError));

    const error = await captureError(startRun(BASE_URL, intent));

    expect(isAmbiguousCreateError(error)).toBe(true);
  });

  it("keeps malformed create JSON as a bounded stable invalid_response", async () => {
    const intent = createRunIntent(() => FIXED_UUID);
    stubFetch(
      new Response("{not-json", {
        headers: { "Content-Type": "application/json" },
        status: 200
      })
    );

    const error = await captureError(startRun(BASE_URL, intent));

    expect(error).toMatchObject({ details: { code: "invalid_response" } });
    expect(isAmbiguousCreateError(error)).toBe(false);
  });

  it.each([
    [
      "structured HTTP error",
      jsonResponse(
        {
          code: "connection_failed",
          problem: "Backend returned a structured error.",
          cause: "The request was rejected after acknowledgement.",
          fix: "Inspect the structured response.",
          retryable: true
        },
        503
      )
    ],
    [
      "idempotency conflict",
      jsonResponse(
        {
          code: "run_idempotency_conflict",
          problem: "The key is already bound to another request.",
          cause: "The immutable create intent changed.",
          fix: "Use the original intent or create a new one.",
          retryable: false
        },
        409
      )
    ],
    [
      "invalid response",
      jsonResponse({
        run_id: "run_live_001",
        segment_id: "run_live_001_seg_000",
        status: "started",
        thread_id: `demo-console-${FIXED_UUID}`
      })
    ]
  ])("does not classify a %s as ambiguous", async (_label, response) => {
    const intent: RunCreateIntent = createRunIntent(() => FIXED_UUID);
    stubFetch(response);

    const error = await captureError(startRun(BASE_URL, intent));

    expect(error).toBeInstanceOf(ClientRequestError);
    expect(isAmbiguousCreateError(error)).toBe(false);
  });
});

describe("loopback request boundary", () => {
  it.each(["health", "create", "status", "result"] as const)(
    "rejects redirects on the %s request path",
    async (requestPath) => {
      const intent = createRunIntent(() => FIXED_UUID);
      const responses = {
        health: jsonResponse({ status: "ok", service: "decision-research-agent" }),
        create: jsonResponse({
          run_id: "run_live_redirect",
          segment_id: "run_live_redirect_seg_000",
          status: "started",
          thread_id: intent.payload.thread_id,
          idempotent_replay: false
        }),
        status: jsonResponse(validRunStatus("run_live_redirect")),
        result: jsonResponse(validRunResult("run_live_redirect"))
      };
      const fetchMock = stubFetch(responses[requestPath]);

      if (requestPath === "health") {
        await getHealth(BASE_URL);
      } else if (requestPath === "create") {
        await startRun(BASE_URL, intent);
      } else if (requestPath === "status") {
        await getRun(BASE_URL, "run_live_redirect");
      } else {
        await getResult(BASE_URL, "run_live_redirect");
      }

      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(fetchMock.mock.calls[0][1]?.redirect).toBe("error");
    }
  );
});

describe("strict live response parsing", () => {
  it("returns only the parsed immutable run projection", async () => {
    stubFetch(
      jsonResponse({
        run_id: "run_live_001",
        thread_id: "demo-console-thread",
        profile_id: "generic",
        execution_status: "completed",
        review_status: "not_required",
        delivery_status: "ready",
        state_version: 2,
        segments: [
          {
            segment_id: "run_live_001_seg_000",
            kind: "initial",
            sequence: 0,
            attempt: 1,
            status: "completed"
          }
        ],
        evidence: [],
        review_workflow: null,
        review_decision: null,
        review_resolution: null,
        failure_cause: null,
        query: "ignored private query"
      })
    );

    const run = await getRun(BASE_URL, "run_live_001");

    expect(run).toEqual({
      run_id: "run_live_001",
      thread_id: "demo-console-thread",
      profile_id: "generic",
      execution_status: "completed",
      review_status: "not_required",
      delivery_status: "ready",
      state_version: 2,
      segments: [
        {
          segment_id: "run_live_001_seg_000",
          kind: "initial",
          sequence: 0,
          attempt: 1,
          status: "completed"
        }
      ],
      evidence: [],
      review: { workflow: null, decision: null, resolution: null },
      failureCause: { kind: "not_applicable" }
    });
    expect("query" in run).toBe(false);
    expect("currentArtifacts" in run).toBe(false);
    expect(Object.isFrozen(run)).toBe(true);
  });

  it("converts malformed selected run fields to bounded invalid_response", async () => {
    stubFetch(
      jsonResponse({
        run_id: "run_live_001",
        thread_id: "demo-console-thread",
        profile_id: "generic",
        execution_status: { raw_error: "opaque selected-field leak" },
        review_status: "not_required",
        delivery_status: "ready",
        state_version: 2,
        segments: [],
        evidence: [],
        review_workflow: null,
        review_decision: null,
        review_resolution: null
      })
    );

    const error = await captureError(getRun(BASE_URL, "run_live_001"));

    expect(error).toBeInstanceOf(ClientRequestError);
    expect(error).toMatchObject({ details: { code: "invalid_response", retryable: false } });
    expect(JSON.stringify((error as ClientRequestError).details)).not.toContain(
      "opaque selected-field leak"
    );
  });

  it("rejects a status response for a different requested run", async () => {
    stubFetch(
      jsonResponse({
        run_id: "run_live_wrong",
        thread_id: "demo-console-thread",
        profile_id: "generic",
        execution_status: "completed",
        review_status: "not_required",
        delivery_status: "ready",
        state_version: 2,
        segments: [],
        evidence: [],
        review_workflow: null,
        review_decision: null,
        review_resolution: null,
        failure_cause: null
      })
    );

    const error = await captureError(getRun(BASE_URL, "run_live_expected"));

    expect(error).toMatchObject({ details: { code: "invalid_response" } });
  });

  it("returns only the parsed immutable canonical result", async () => {
    stubFetch(
      jsonResponse({
        run_id: "run_live_001",
        execution_status: "completed",
        delivery_status: "ready",
        artifact: {
          artifact_id: "research-report.md",
          kind: "research_report_markdown",
          media_type: "text/markdown",
          content: "# Canonical result",
          content_hash: "sha256:def",
          local_path: "/private/result.md"
        },
        unknown_private_field: "ignored"
      })
    );

    const result = await getResult(BASE_URL, "run_live_001");

    expect(result).toEqual({
      run_id: "run_live_001",
      execution_status: "completed",
      delivery_status: "ready",
      artifact: {
        artifact_id: "research-report.md",
        kind: "research_report_markdown",
        media_type: "text/markdown",
        content: "# Canonical result",
        content_hash: "sha256:def"
      }
    });
    expect("local_path" in result.artifact).toBe(false);
    expect(Object.isFrozen(result)).toBe(true);
  });

  it("converts malformed canonical artifact fields to bounded invalid_response", async () => {
    stubFetch(
      jsonResponse({
        run_id: "run_live_001",
        execution_status: "completed",
        delivery_status: "ready",
        artifact: {
          artifact_id: "research-report.md",
          kind: "research_report_markdown",
          media_type: "text/markdown",
          content: { raw_error: "opaque artifact leak" },
          content_hash: "sha256:def"
        }
      })
    );

    const error = await captureError(getResult(BASE_URL, "run_live_001"));

    expect(error).toBeInstanceOf(ClientRequestError);
    expect(error).toMatchObject({ details: { code: "invalid_response", retryable: false } });
    expect(JSON.stringify((error as ClientRequestError).details)).not.toContain(
      "opaque artifact leak"
    );
  });

  it("rejects a canonical result for a different requested run", async () => {
    stubFetch(
      jsonResponse({
        run_id: "run_live_wrong",
        execution_status: "completed",
        delivery_status: "ready",
        artifact: {
          artifact_id: "research-report.md",
          kind: "research_report_markdown",
          media_type: "text/markdown",
          content: "# Wrong run result",
          content_hash: "sha256:wrong"
        }
      })
    );

    const error = await captureError(getResult(BASE_URL, "run_live_expected"));

    expect(error).toMatchObject({ details: { code: "invalid_response" } });
  });
});

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
    status
  });
}

function jsonReadFailureResponse(error: unknown): Response {
  return {
    json: () => Promise.reject(error),
    ok: true,
    status: 200
  } as Response;
}

function validRunStatus(runId: string) {
  return {
    run_id: runId,
    thread_id: "demo-console-thread",
    profile_id: "generic",
    execution_status: "completed",
    review_status: "not_required",
    delivery_status: "ready",
    state_version: 2,
    segments: [],
    evidence: [],
    review_workflow: null,
    review_decision: null,
    review_resolution: null,
    failure_cause: null
  };
}

function validRunResult(runId: string) {
  return {
    run_id: runId,
    execution_status: "completed",
    delivery_status: "ready",
    artifact: {
      artifact_id: "research-report.md",
      kind: "research_report_markdown",
      media_type: "text/markdown",
      content: "# Canonical result",
      content_hash: "sha256:def"
    }
  };
}

function stubFetch(response: Response | Promise<Response>) {
  const fetchMock = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) =>
    Promise.resolve(response)
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

async function captureError(promise: Promise<unknown>) {
  try {
    await promise;
  } catch (error) {
    return error;
  }
  throw new Error("Expected promise to reject.");
}
