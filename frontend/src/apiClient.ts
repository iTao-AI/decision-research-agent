export const DEFAULT_BACKEND_BASE_URL = "http://127.0.0.1:8000";

export type ClientError = {
  code: string;
  problem: string;
  cause: string;
  fix: string;
  retryable: boolean;
  run_id?: string;
};

export type HealthResponse = {
  service: string;
  status: string;
};

export type RunCreationResponse = {
  run_id: string;
  segment_id: string;
  status: string;
  thread_id: string;
};

export type RunProjection = {
  delivery_status?: string;
  execution_status?: string;
  review_status?: string;
  run_id: string;
  state_version?: number;
};

export type RunResultResponse = {
  artifact?: {
    artifact_id?: string;
    content?: string;
    content_hash?: string;
    kind?: string;
    media_type?: string;
  };
  delivery_status?: string;
  execution_status?: string;
  run_id: string;
};

export class ClientRequestError extends Error {
  details: ClientError;

  constructor(details: ClientError) {
    super(details.code);
    this.details = details;
  }
}

export async function getHealth(baseUrl: string, signal?: AbortSignal): Promise<HealthResponse> {
  const value = await requestJson<Partial<HealthResponse>>(baseUrl, "/health", {
    method: "GET",
    signal
  });
  if (typeof value.status !== "string" || typeof value.service !== "string") {
    throw new ClientRequestError(invalidResponse("Health response did not include status/service."));
  }
  if (value.service !== "decision-research-agent") {
    throw new ClientRequestError({
      code: "service_identity_mismatch",
      problem: "The endpoint is not Decision Research Agent.",
      cause: "The health response returned an unexpected service identity.",
      fix: "Use the local Decision Research Agent backend endpoint.",
      retryable: false
    });
  }
  if (value.status !== "ok") {
    throw new ClientRequestError({
      code: "backend_not_ready",
      problem: "Decision Research Agent is not ready.",
      cause: "The health response status was not ok.",
      fix: "Recover the local backend before starting a demonstration run.",
      retryable: true
    });
  }
  return {
    service: value.service,
    status: value.status
  };
}

export async function startRun(baseUrl: string, signal?: AbortSignal): Promise<RunCreationResponse> {
  const value = await requestJson<Partial<RunCreationResponse>>(baseUrl, "/api/runs", {
    body: JSON.stringify({
      profile_id: "generic",
      query: "Generate a short evidence-bound result for the Agent Research Operations Console.",
      scope: {},
      thread_id: `demo-console-${Date.now()}`
    }),
    headers: { "Content-Type": "application/json" },
    method: "POST",
    signal
  });
  if (
    typeof value.run_id !== "string" ||
    typeof value.segment_id !== "string" ||
    typeof value.status !== "string" ||
    typeof value.thread_id !== "string"
  ) {
    throw new ClientRequestError(invalidResponse("Run creation response did not include run identity."));
  }
  return {
    run_id: value.run_id,
    segment_id: value.segment_id,
    status: value.status,
    thread_id: value.thread_id
  };
}

export async function getRun(
  baseUrl: string,
  runId: string,
  signal?: AbortSignal
): Promise<RunProjection> {
  const value = await requestJson<Partial<RunProjection>>(
    baseUrl,
    `/api/runs/${encodeURIComponent(runId)}`,
    { method: "GET", signal }
  );
  if (typeof value.run_id !== "string") {
    throw new ClientRequestError(invalidResponse("Run projection did not include run_id."));
  }
  return {
    delivery_status: stringOrUndefined(value.delivery_status),
    execution_status: stringOrUndefined(value.execution_status),
    review_status: stringOrUndefined(value.review_status),
    run_id: value.run_id,
    state_version: typeof value.state_version === "number" ? value.state_version : undefined
  };
}

export async function getResult(
  baseUrl: string,
  runId: string,
  signal?: AbortSignal
): Promise<RunResultResponse> {
  const value = await requestJson<Partial<RunResultResponse>>(
    baseUrl,
    `/api/runs/${encodeURIComponent(runId)}/result`,
    { method: "GET", signal }
  );
  if (typeof value.run_id !== "string") {
    throw new ClientRequestError(invalidResponse("Canonical result response did not include run_id."));
  }
  return {
    artifact: typeof value.artifact === "object" && value.artifact !== null ? value.artifact : undefined,
    delivery_status: stringOrUndefined(value.delivery_status),
    execution_status: stringOrUndefined(value.execution_status),
    run_id: value.run_id
  };
}

export function normalizeClientError(error: unknown, runId?: string): ClientError {
  if (error instanceof ClientRequestError) {
    return runId && !error.details.run_id ? { ...error.details, run_id: runId } : error.details;
  }
  return {
    code: "connection_failed",
    problem: "Cannot reach Decision Research Agent.",
    cause: "The configured service endpoint is unavailable.",
    fix: "Start the backend or verify Backend base URL.",
    retryable: true,
    ...(runId ? { run_id: runId } : {})
  };
}

async function requestJson<T>(baseUrl: string, path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(buildUrl(baseUrl, path), init ?? { method: "GET" });
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }
    throw new ClientRequestError(normalizeClientError(error));
  }

  const body = await readJson(response);
  if (!response.ok) {
    throw new ClientRequestError(normalizeServerError(body, response.status));
  }
  if (body === null || typeof body !== "object" || Array.isArray(body)) {
    throw new ClientRequestError(invalidResponse("Response body was not a JSON object."));
  }
  return body as T;
}

function buildUrl(baseUrl: string, path: string) {
  const trimmedBase = baseUrl.trim();
  if (!/^http:\/\/127\.0\.0\.1:\d{1,5}\/?$/.test(trimmedBase)) {
    throw new ClientRequestError(invalidBackendUrl());
  }
  let parsed: URL;
  try {
    parsed = new URL(trimmedBase);
  } catch {
    throw new ClientRequestError(invalidBackendUrl());
  }
  if (
    parsed.protocol !== "http:" ||
    parsed.hostname !== "127.0.0.1" ||
    parsed.port === "" ||
    parsed.username !== "" ||
    parsed.password !== "" ||
    parsed.pathname !== "/" ||
    parsed.search !== "" ||
    parsed.hash !== ""
  ) {
    throw new ClientRequestError(invalidBackendUrl());
  }
  return `${parsed.origin}${path}`;
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function normalizeServerError(body: unknown, status: number): ClientError {
  if (body !== null && typeof body === "object" && !Array.isArray(body)) {
    const record = body as Record<string, unknown>;
    return {
      code: typeof record.code === "string" ? record.code : `http_${status}`,
      problem: typeof record.problem === "string" ? record.problem : "Backend returned an error.",
      cause: typeof record.cause === "string" ? record.cause : "The request could not be completed.",
      fix: typeof record.fix === "string" ? record.fix : "Inspect the run state or retry after recovery.",
      retryable: typeof record.retryable === "boolean" ? record.retryable : status >= 500,
      ...(typeof record.run_id === "string" ? { run_id: record.run_id } : {})
    };
  }
  return {
    code: `http_${status}`,
    problem: "Backend returned an error.",
    cause: "The response did not include a structured error envelope.",
    fix: "Check backend logs locally and retry from the console.",
    retryable: status >= 500
  };
}

function invalidResponse(cause: string): ClientError {
  return {
    code: "invalid_response",
    problem: "Backend response could not be rendered safely.",
    cause,
    fix: "Verify the backend version and API contract.",
    retryable: false
  };
}

function invalidBackendUrl(): ClientError {
  return {
    code: "invalid_backend_url",
    problem: "Backend base URL is outside the local demo boundary.",
    cause:
      "Live Backend only accepts http://127.0.0.1:<port> without credentials, path, query, or fragment.",
    fix: "Enter an explicit loopback HTTP endpoint such as http://127.0.0.1:8000.",
    retryable: false
  };
}

function stringOrUndefined(value: unknown) {
  return typeof value === "string" ? value : undefined;
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}
