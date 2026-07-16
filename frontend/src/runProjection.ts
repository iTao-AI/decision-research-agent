export type FailureCauseAvailability =
  | Readonly<{ kind: "unsupported" }>
  | Readonly<{ kind: "not_applicable" }>
  | Readonly<{
      kind: "not_observed";
      schema_version: "dra.run-failure-cause.v1";
    }>
  | Readonly<{
      kind: "observed";
      schema_version: "dra.run-failure-cause.v1";
      phase: string;
      code: string;
      recorded_at: string;
    }>;

export type RunSegmentProjection = Readonly<{
  segment_id: string;
  kind: string;
  sequence: number;
  attempt: number;
  status: string;
}>;

export type RunEvidenceProjection = Readonly<{
  evidence_id: string;
  source_url: string | null;
  source_identity: string;
  evidence_fingerprint: string;
  citation_status: string;
  verification_status: string;
}>;

export type ReviewWorkflowProjection = Readonly<{
  workflow_id: string;
  review_id: string;
  review_revision: number;
  status: string;
  decision_id: string | null;
  post_review_segment_id: string | null;
  attempt_count: number;
  last_error_code: string | null;
  created_at: string;
  updated_at: string;
}>;

export type ReviewDecisionProjection = Readonly<{
  decision_id: string;
  review_id: string;
  review_revision: number;
  action: string;
  reason_recorded: boolean;
  accepted_state_version: number;
  created_at: string;
}>;

export type ReviewResolutionProjection = Readonly<{
  resolution_id: string;
  review_id: string;
  decision_id: string;
  action: string;
  artifact_ids: readonly string[];
  created_at: string;
}>;

export type ReviewPresenceProjection = Readonly<{
  workflow: ReviewWorkflowProjection | null;
  decision: ReviewDecisionProjection | null;
  resolution: ReviewResolutionProjection | null;
}>;

export type VerificationSummaryProjection = Readonly<{
  state_counts: Readonly<Record<string, number>>;
  origin_counts: Readonly<Record<string, number>>;
  snapshot_hash: string | null;
}>;

export type CurrentPublicationProjection = Readonly<{
  publication_id: string;
  revision: number;
  status: string;
  artifact_ids: readonly string[];
}>;

export type ArtifactMetadataProjection = Readonly<{
  artifact_id: string;
  kind: string;
  media_type: string;
  content_hash: string;
  created_at: string;
}>;

export type RunProjection = Readonly<{
  run_id: string;
  thread_id: string;
  profile_id: string;
  execution_status: string;
  review_status: string;
  delivery_status: string;
  state_version: number;
  segments: readonly RunSegmentProjection[];
  evidence: readonly RunEvidenceProjection[];
  review: ReviewPresenceProjection;
  verification?: VerificationSummaryProjection;
  currentPublication?: CurrentPublicationProjection;
  currentArtifacts: readonly ArtifactMetadataProjection[];
  failureCause: FailureCauseAvailability;
}>;

export type CanonicalArtifactProjection = Readonly<{
  artifact_id: string;
  kind: string;
  media_type: string;
  content: string;
  content_hash: string;
}>;

export type RunResultResponse = Readonly<{
  run_id: string;
  execution_status: string;
  delivery_status: string;
  artifact: CanonicalArtifactProjection;
}>;

const FAILURE_CAUSE_SCHEMA_VERSION = "dra.run-failure-cause.v1" as const;
const FAILURE_CAUSE_CODES = {
  dispatch: new Set([
    "run_dispatch_schedule_failed",
    "run_dispatch_start_failed",
    "run_dispatch_start_timeout",
    "run_dispatch_lease_expired"
  ]),
  execution: new Set([
    "call_budget_exceeded",
    "recursion_limit_exceeded",
    "invalid_research_packet",
    "missing_research_packet",
    "run_timeout",
    "cancelled",
    "execution_error"
  ]),
  finalization: new Set(["run_timeout", "cancelled", "run_finalization_failed"])
} as const;

type FailureCausePhase = keyof typeof FAILURE_CAUSE_CODES;

export function parseRunProjection(value: unknown): RunProjection {
  const record = expectRecord(value);
  const verification = hasOwn(record, "verification_summary")
    ? parseVerificationSummary(record.verification_summary)
    : undefined;
  const currentPublication = hasOwn(record, "current_publication")
    ? parseCurrentPublication(record.current_publication)
    : undefined;

  return Object.freeze({
    run_id: expectString(record.run_id),
    thread_id: expectString(record.thread_id),
    profile_id: expectString(record.profile_id),
    execution_status: expectString(record.execution_status),
    review_status: expectString(record.review_status),
    delivery_status: expectString(record.delivery_status),
    state_version: expectInteger(record.state_version),
    segments: Object.freeze(expectArray(record.segments).map(parseRunSegment)),
    evidence: Object.freeze(expectArray(record.evidence).map(parseRunEvidence)),
    review: Object.freeze({
      workflow: parseReviewWorkflow(record.review_workflow),
      decision: parseReviewDecision(record.review_decision),
      resolution: parseReviewResolution(record.review_resolution)
    }),
    ...(verification === undefined ? {} : { verification }),
    ...(currentPublication === undefined ? {} : { currentPublication }),
    currentArtifacts: hasOwn(record, "current_artifacts")
      ? Object.freeze(expectArray(record.current_artifacts).map(parseArtifactMetadata))
      : Object.freeze([] as ArtifactMetadataProjection[]),
    failureCause: parseFailureCause(record)
  });
}

export function parseRunResult(value: unknown): RunResultResponse {
  const record = expectRecord(value);
  const artifact = expectRecord(record.artifact);

  return Object.freeze({
    run_id: expectString(record.run_id),
    execution_status: expectString(record.execution_status),
    delivery_status: expectString(record.delivery_status),
    artifact: Object.freeze({
      artifact_id: expectString(artifact.artifact_id),
      kind: expectString(artifact.kind),
      media_type: expectString(artifact.media_type),
      content: expectString(artifact.content),
      content_hash: expectString(artifact.content_hash)
    })
  });
}

function parseRunSegment(value: unknown): RunSegmentProjection {
  const record = expectRecord(value);
  return Object.freeze({
    segment_id: expectString(record.segment_id),
    kind: expectString(record.kind),
    sequence: expectInteger(record.sequence),
    attempt: expectInteger(record.attempt),
    status: expectString(record.status)
  });
}

function parseRunEvidence(value: unknown): RunEvidenceProjection {
  const record = expectRecord(value);
  return Object.freeze({
    evidence_id: expectString(record.evidence_id),
    source_url: expectNullableString(record.source_url),
    source_identity: expectString(record.source_identity),
    evidence_fingerprint: expectString(record.evidence_fingerprint),
    citation_status: expectString(record.citation_status),
    verification_status: expectString(record.verification_status)
  });
}

function parseReviewWorkflow(value: unknown): ReviewWorkflowProjection | null {
  if (value === null) {
    return null;
  }
  const record = expectRecord(value);
  return Object.freeze({
    workflow_id: expectString(record.workflow_id),
    review_id: expectString(record.review_id),
    review_revision: expectInteger(record.review_revision),
    status: expectString(record.status),
    decision_id: expectNullableString(record.decision_id),
    post_review_segment_id: expectNullableString(record.post_review_segment_id),
    attempt_count: expectInteger(record.attempt_count),
    last_error_code: expectNullableString(record.last_error_code),
    created_at: expectString(record.created_at),
    updated_at: expectString(record.updated_at)
  });
}

function parseReviewDecision(value: unknown): ReviewDecisionProjection | null {
  if (value === null) {
    return null;
  }
  const record = expectRecord(value);
  return Object.freeze({
    decision_id: expectString(record.decision_id),
    review_id: expectString(record.review_id),
    review_revision: expectInteger(record.review_revision),
    action: expectString(record.action),
    reason_recorded: expectBoolean(record.reason_recorded),
    accepted_state_version: expectInteger(record.accepted_state_version),
    created_at: expectString(record.created_at)
  });
}

function parseReviewResolution(value: unknown): ReviewResolutionProjection | null {
  if (value === null) {
    return null;
  }
  const record = expectRecord(value);
  return Object.freeze({
    resolution_id: expectString(record.resolution_id),
    review_id: expectString(record.review_id),
    decision_id: expectString(record.decision_id),
    action: expectString(record.action),
    artifact_ids: parseStringArray(record.artifact_ids),
    created_at: expectString(record.created_at)
  });
}

function parseVerificationSummary(value: unknown): VerificationSummaryProjection {
  const record = expectRecord(value);
  return Object.freeze({
    state_counts: parseCountsMap(record.state_counts),
    origin_counts: parseCountsMap(record.origin_counts),
    snapshot_hash: expectNullableString(record.snapshot_hash)
  });
}

function parseCurrentPublication(value: unknown): CurrentPublicationProjection {
  const record = expectRecord(value);
  return Object.freeze({
    publication_id: expectString(record.publication_id),
    revision: expectInteger(record.revision),
    status: expectString(record.status),
    artifact_ids: parseStringArray(record.artifact_ids)
  });
}

function parseArtifactMetadata(value: unknown): ArtifactMetadataProjection {
  const record = expectRecord(value);
  return Object.freeze({
    artifact_id: expectString(record.artifact_id),
    kind: expectString(record.kind),
    media_type: expectString(record.media_type),
    content_hash: expectString(record.content_hash),
    created_at: expectString(record.created_at)
  });
}

function parseFailureCause(record: Record<string, unknown>): FailureCauseAvailability {
  if (!hasOwn(record, "failure_cause")) {
    return Object.freeze({ kind: "unsupported" });
  }
  if (record.failure_cause === null) {
    return Object.freeze({ kind: "not_applicable" });
  }

  const failureCause = expectRecord(record.failure_cause);
  if (expectString(failureCause.schema_version) !== FAILURE_CAUSE_SCHEMA_VERSION) {
    return invalidResponse();
  }
  const observationStatus = expectString(failureCause.observation_status);
  if (observationStatus === "not_observed") {
    return Object.freeze({
      kind: "not_observed",
      schema_version: FAILURE_CAUSE_SCHEMA_VERSION
    });
  }
  if (observationStatus !== "observed") {
    return invalidResponse();
  }

  const phase = expectString(failureCause.phase);
  const code = expectString(failureCause.code);
  if (!hasOwn(FAILURE_CAUSE_CODES, phase)) {
    return invalidResponse();
  }
  if (!FAILURE_CAUSE_CODES[phase as FailureCausePhase].has(code)) {
    return invalidResponse();
  }
  return Object.freeze({
    kind: "observed",
    schema_version: FAILURE_CAUSE_SCHEMA_VERSION,
    phase,
    code,
    recorded_at: expectString(failureCause.recorded_at)
  });
}

function expectRecord(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return invalidResponse();
  }
  return value as Record<string, unknown>;
}

function expectString(value: unknown): string {
  if (typeof value !== "string") {
    return invalidResponse();
  }
  return value;
}

function expectInteger(value: unknown): number {
  if (typeof value !== "number" || !Number.isInteger(value)) {
    return invalidResponse();
  }
  return value;
}

function expectNullableString(value: unknown): string | null {
  if (value === null) {
    return null;
  }
  return expectString(value);
}

function expectArray(value: unknown): unknown[] {
  if (!Array.isArray(value)) {
    return invalidResponse();
  }
  return value;
}

function expectBoolean(value: unknown): boolean {
  if (typeof value !== "boolean") {
    return invalidResponse();
  }
  return value;
}

function parseCountsMap(value: unknown): Readonly<Record<string, number>> {
  const record = expectRecord(value);
  const counts: Record<string, number> = {};
  for (const [key, count] of Object.entries(record)) {
    if (typeof count !== "number" || !Number.isInteger(count) || count < 0) {
      return invalidResponse();
    }
    counts[key] = count;
  }
  return Object.freeze(counts);
}

function parseStringArray(value: unknown): readonly string[] {
  return Object.freeze(expectArray(value).map(expectString));
}

function hasOwn(record: object, key: PropertyKey): boolean {
  return Object.prototype.hasOwnProperty.call(record, key);
}

function invalidResponse(): never {
  throw new Error("invalid_response");
}
