import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ClientRequestError,
  createRunIntent,
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

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
    status
  });
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
