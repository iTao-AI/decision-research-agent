import { useCallback, useRef, useState } from "react";

import {
  DEFAULT_BACKEND_BASE_URL,
  ClientRequestError,
  createRunIntent,
  getHealth,
  getResult,
  getRun,
  isAmbiguousCreateError,
  normalizeClientError,
  startRun,
  type ClientError,
  type HealthResponse,
  type RunCreateIntent,
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
  | "creating"
  | "reconciliation_required"
  | "polling"
  | "observation_interrupted"
  | "terminal"
  | "result"
  | "error";

export type LiveRunOptions = {
  pollIntervalMs?: number;
  randomUUID?: () => string;
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
const DEFAULT_RANDOM_UUID = () => crypto.randomUUID();
const TERMINAL_STATUSES = new Set([
  "completed",
  "completed_with_fallback",
  "failed",
  "cancelled",
  "timeout",
  "timed_out",
  "review_required",
  "blocked"
]);

export function useLiveRun(options: LiveRunOptions = {}) {
  const pollIntervalMs = options.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS;
  const randomUUID = options.randomUUID ?? DEFAULT_RANDOM_UUID;
  const waitTimeoutMs = options.waitTimeoutMs ?? DEFAULT_WAIT_TIMEOUT_MS;
  const requestVersion = useRef(0);
  const activeController = useRef<AbortController | null>(null);
  const createIntent = useRef<RunCreateIntent | null>(null);
  const activeRunId = useRef<string | null>(null);
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
  const clearRunScope = useCallback(() => {
    createIntent.current = null;
    activeRunId.current = null;
  }, []);

  const setMode = useCallback(
    (mode: DemoMode) => {
      invalidateRequests();
      clearRunScope();
      setState((current) => ({
        baseUrl: current.baseUrl,
        mode,
        status: mode === "static" ? "static" : "idle"
      }));
    },
    [clearRunScope, invalidateRequests]
  );

  const setBaseUrl = useCallback(
    (baseUrl: string) => {
      invalidateRequests();
      clearRunScope();
      setState((current) => ({
        baseUrl,
        mode: current.mode,
        status: current.mode === "static" ? "static" : "idle"
      }));
    },
    [clearRunScope, invalidateRequests]
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

  const observeRun = useCallback(
    async ({
      baseUrl,
      deadlineAt,
      runId,
      signal,
      version
    }: {
      baseUrl: string;
      deadlineAt: number;
      runId: string;
      signal: AbortSignal;
      version: number;
    }) => {
      while (isCurrent(version)) {
        const remainingBeforePoll = deadlineAt - Date.now();
        if (remainingBeforePoll <= 0) {
          throw new ClientRequestError(runWaitTimeout(runId));
        }
        const run = await getRun(baseUrl, runId, signal);
        if (!isCurrent(version)) {
          return;
        }
        setState((current) => ({
          ...current,
          error: undefined,
          run,
          status: "polling"
        }));

        if (run.delivery_status === "ready") {
          const result = await getResult(baseUrl, runId, signal);
          if (!isCurrent(version)) {
            return;
          }
          setState((current) => ({
            ...current,
            error: undefined,
            result,
            run,
            status: "result"
          }));
          return;
        }

        if (isTerminal(run.execution_status)) {
          setState((current) => ({
            ...current,
            error: undefined,
            result: undefined,
            run,
            status: "terminal"
          }));
          return;
        }

        const remainingMs = deadlineAt - Date.now();
        if (remainingMs <= 0) {
          throw new ClientRequestError(runWaitTimeout(runId));
        }
        await sleep(Math.min(pollIntervalMs, remainingMs), signal);
      }
    },
    [isCurrent, pollIntervalMs]
  );

  const createAndObserve = useCallback(async (intent: RunCreateIntent) => {
    const { controller: requestController, version } = nextRequest();
    const deadline = createDeadline(requestController.signal, waitTimeoutMs);
    const baseUrl = state.baseUrl;
    let acknowledgedRunId: string | undefined;
    setState((current) => ({
      ...current,
      created: undefined,
      error: undefined,
      mode: "live",
      result: undefined,
      run: undefined,
      status: "creating"
    }));
    try {
      const created = await startRun(baseUrl, intent, deadline.signal);
      acknowledgedRunId = created.run_id;
      if (!isCurrent(version)) {
        return;
      }
      createIntent.current = null;
      activeRunId.current = created.run_id;
      setState((current) => ({
        ...current,
        created,
        error: undefined,
        status: "polling"
      }));

      await observeRun({
        baseUrl,
        deadlineAt: deadline.deadlineAt,
        runId: created.run_id,
        signal: deadline.signal,
        version
      });
    } catch (error) {
      if (!isCurrent(version)) {
        return;
      }
      if (!acknowledgedRunId && isAmbiguousCreateError(error)) {
        setState((current) => ({
          ...current,
          error: normalizeClientError(error),
          status: "reconciliation_required"
        }));
        return;
      }
      if (!acknowledgedRunId) {
        createIntent.current = null;
        activeRunId.current = null;
        setState((current) => ({
          ...current,
          error: normalizeClientError(error),
          status: "error"
        }));
        return;
      }
      const failure = classifyObservationFailure(
        error,
        acknowledgedRunId,
        deadline.didExpire()
      );
      setState((current) => ({
        ...current,
        ...failure
      }));
    } finally {
      deadline.dispose();
    }
  }, [isCurrent, nextRequest, observeRun, state.baseUrl, waitTimeoutMs]);

  const startNewRun = useCallback(async () => {
    const intent = createRunIntent(randomUUID);
    createIntent.current = intent;
    activeRunId.current = null;
    await createAndObserve(intent);
  }, [createAndObserve, randomUUID]);

  const retryCreate = useCallback(async () => {
    const intent = createIntent.current;
    if (!intent) {
      return;
    }
    await createAndObserve(intent);
  }, [createAndObserve]);

  const discardPendingIntent = useCallback(() => {
    invalidateRequests();
    createIntent.current = null;
    activeRunId.current = null;
    setState((current) => ({
      baseUrl: current.baseUrl,
      ...(current.health ? { health: current.health } : {}),
      mode: current.mode,
      status: current.mode === "static" ? "static" : current.health ? "ready" : "idle"
    }));
  }, [invalidateRequests]);

  const resumeObservation = useCallback(async () => {
    const runId = activeRunId.current;
    if (!runId) {
      return;
    }
    const { controller: requestController, version } = nextRequest();
    const deadline = createDeadline(requestController.signal, waitTimeoutMs);
    const baseUrl = state.baseUrl;
    setState((current) => ({
      ...current,
      error: undefined,
      result: undefined,
      status: "polling"
    }));
    try {
      await observeRun({
        baseUrl,
        deadlineAt: deadline.deadlineAt,
        runId,
        signal: deadline.signal,
        version
      });
    } catch (error) {
      if (!isCurrent(version)) {
        return;
      }
      const failure = classifyObservationFailure(error, runId, deadline.didExpire());
      setState((current) => ({
        ...current,
        ...failure
      }));
    } finally {
      deadline.dispose();
    }
  }, [isCurrent, nextRequest, observeRun, state.baseUrl, waitTimeoutMs]);

  return {
    checkHealth,
    discardPendingIntent,
    resumeObservation,
    retryCreate,
    runGoldenPath: startNewRun,
    setBaseUrl,
    setMode,
    startNewRun,
    state
  };
}

function isTerminal(status: string | undefined) {
  return typeof status === "string" && TERMINAL_STATUSES.has(status);
}

function classifyObservationFailure(
  error: unknown,
  runId: string,
  deadlineExpired: boolean
): Pick<LiveRunState, "error" | "status"> {
  const isRunWaitTimeout =
    error instanceof ClientRequestError && error.details.code === "run_wait_timeout";
  if (!isAmbiguousCreateError(error) && !isRunWaitTimeout) {
    return {
      error: normalizeClientError(error, runId),
      status: "error"
    };
  }
  const isDeadlineAbort =
    deadlineExpired && error instanceof DOMException && error.name === "AbortError";
  return {
    error: isDeadlineAbort ? runWaitTimeout(runId) : normalizeClientError(error, runId),
    status: "observation_interrupted"
  };
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
