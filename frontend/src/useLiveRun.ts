import { useCallback, useRef, useState } from "react";

import {
  DEFAULT_BACKEND_BASE_URL,
  ClientRequestError,
  getHealth,
  getResult,
  getRun,
  normalizeClientError,
  startRun,
  type ClientError,
  type HealthResponse,
  type RunCreationResponse,
  type RunProjection,
  type RunResultResponse
} from "./apiClient";

export type DemoMode = "static" | "live";
export type LiveStatus =
  | "static"
  | "idle"
  | "checking"
  | "ready"
  | "starting"
  | "polling"
  | "result"
  | "error";

export type LiveRunOptions = {
  pollIntervalMs?: number;
  waitTimeoutMs?: number;
};

export type LiveRunState = {
  baseUrl: string;
  created?: RunCreationResponse;
  error?: ClientError;
  health?: HealthResponse;
  mode: DemoMode;
  result?: RunResultResponse;
  run?: RunProjection;
  status: LiveStatus;
};

const DEFAULT_POLL_INTERVAL_MS = 1000;
const DEFAULT_WAIT_TIMEOUT_MS = 600_000;
const TERMINAL_STATUSES = new Set([
  "completed",
  "completed_with_fallback",
  "failed",
  "cancelled",
  "timeout",
  "timed_out"
]);

export function useLiveRun(options: LiveRunOptions = {}) {
  const pollIntervalMs = options.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS;
  const waitTimeoutMs = options.waitTimeoutMs ?? DEFAULT_WAIT_TIMEOUT_MS;
  const requestVersion = useRef(0);
  const activeController = useRef<AbortController | null>(null);
  const [state, setState] = useState<LiveRunState>({
    baseUrl: DEFAULT_BACKEND_BASE_URL,
    mode: "static",
    status: "static"
  });

  const isCurrent = useCallback((version: number) => requestVersion.current === version, []);
  const invalidateRequests = useCallback(() => {
    activeController.current?.abort();
    activeController.current = null;
    requestVersion.current += 1;
    return requestVersion.current;
  }, []);
  const nextRequest = useCallback(() => {
    invalidateRequests();
    const controller = new AbortController();
    activeController.current = controller;
    return { controller, version: requestVersion.current };
  }, [invalidateRequests]);

  const setMode = useCallback(
    (mode: DemoMode) => {
      invalidateRequests();
      setState((current) => ({
        baseUrl: current.baseUrl,
        mode,
        status: mode === "static" ? "static" : "idle"
      }));
    },
    [invalidateRequests]
  );

  const setBaseUrl = useCallback(
    (baseUrl: string) => {
      invalidateRequests();
      setState((current) => ({
        baseUrl,
        mode: current.mode,
        status: current.mode === "static" ? "static" : "idle"
      }));
    },
    [invalidateRequests]
  );

  const checkHealth = useCallback(async () => {
    const { controller, version } = nextRequest();
    const baseUrl = state.baseUrl;
    setState((current) => ({ ...current, error: undefined, mode: "live", status: "checking" }));
    try {
      const health = await getHealth(baseUrl, controller.signal);
      if (!isCurrent(version)) {
        return;
      }
      setState((current) => ({
        ...current,
        error: undefined,
        health,
        mode: "live",
        status: "ready"
      }));
    } catch (error) {
      if (!isCurrent(version)) {
        return;
      }
      setState((current) => ({
        ...current,
        error: normalizeClientError(error),
        mode: "live",
        status: "error"
      }));
    }
  }, [isCurrent, nextRequest, state.baseUrl]);

  const runGoldenPath = useCallback(async () => {
    const { controller: requestController, version } = nextRequest();
    const deadline = createDeadline(requestController.signal, waitTimeoutMs);
    const baseUrl = state.baseUrl;
    let activeRunId: string | undefined;
    setState((current) => ({
      ...current,
      created: undefined,
      error: undefined,
      mode: "live",
      result: undefined,
      run: undefined,
      status: "starting"
    }));
    try {
      const created = await startRun(baseUrl, deadline.signal);
      activeRunId = created.run_id;
      if (!isCurrent(version)) {
        return;
      }
      setState((current) => ({ ...current, created, status: "polling" }));

      const run = await pollRun({
        baseUrl,
        isCurrent: () => isCurrent(version),
        pollIntervalMs,
        runId: created.run_id,
        signal: deadline.signal,
        deadlineAt: deadline.deadlineAt
      });
      if (!isCurrent(version)) {
        return;
      }
      setState((current) => ({ ...current, run }));

      const result = await getResult(baseUrl, created.run_id, deadline.signal);
      if (!isCurrent(version)) {
        return;
      }
      setState((current) => ({
        ...current,
        result,
        run,
        status: "result"
      }));
    } catch (error) {
      if (!isCurrent(version)) {
        return;
      }
      setState((current) => ({
        ...current,
        error: deadline.didExpire()
          ? runWaitTimeout(activeRunId)
          : normalizeClientError(error, activeRunId),
        status: "error"
      }));
    } finally {
      deadline.dispose();
    }
  }, [isCurrent, nextRequest, pollIntervalMs, state.baseUrl, waitTimeoutMs]);

  return {
    checkHealth,
    runGoldenPath,
    setBaseUrl,
    setMode,
    state
  };
}

async function pollRun({
  baseUrl,
  isCurrent,
  pollIntervalMs,
  runId,
  signal,
  deadlineAt
}: {
  baseUrl: string;
  isCurrent: () => boolean;
  pollIntervalMs: number;
  runId: string;
  signal: AbortSignal;
  deadlineAt: number;
}) {
  while (isCurrent()) {
    const remainingBeforePoll = deadlineAt - Date.now();
    if (remainingBeforePoll <= 0) {
      throw new ClientRequestError(runWaitTimeout(runId));
    }
    const run = await getRun(baseUrl, runId, signal);
    if (isTerminal(run.execution_status)) {
      return run;
    }
    const remainingMs = deadlineAt - Date.now();
    if (remainingMs <= 0) {
      throw new ClientRequestError(runWaitTimeout(runId));
    }
    await sleep(Math.min(pollIntervalMs, remainingMs), signal);
  }
  throw new Error("stale_request");
}

function isTerminal(status: string | undefined) {
  return typeof status === "string" && TERMINAL_STATUSES.has(status);
}

function sleep(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const timer = window.setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      window.clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

function createDeadline(parentSignal: AbortSignal, waitTimeoutMs: number) {
  const controller = new AbortController();
  let expired = false;
  const deadlineAt = Date.now() + waitTimeoutMs;
  const abortFromParent = () => controller.abort();
  parentSignal.addEventListener("abort", abortFromParent, { once: true });
  const timer = window.setTimeout(() => {
    expired = true;
    controller.abort();
  }, waitTimeoutMs);
  return {
    deadlineAt,
    didExpire: () => expired,
    dispose: () => {
      window.clearTimeout(timer);
      parentSignal.removeEventListener("abort", abortFromParent);
    },
    signal: controller.signal
  };
}

function runWaitTimeout(runId?: string): ClientError {
  return {
    code: "run_wait_timeout",
    problem: "Research run did not reach a terminal result before the client deadline.",
    cause: "The bounded browser wait expired.",
    fix: "The server-side run may still continue; check the run again by run_id.",
    retryable: true,
    ...(runId ? { run_id: runId } : {})
  };
}
