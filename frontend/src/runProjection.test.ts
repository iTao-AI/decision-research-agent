import { describe, expect, it } from "vitest";

import { parseRunProjection, parseRunResult } from "./runProjection";

const STATUS = {
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
  evidence: [
    {
      evidence_id: "ev_001",
      source_url: "https://example.com/source",
      source_identity: "https://example.com/source",
      evidence_fingerprint: "sha256:abc",
      citation_status: "cited",
      verification_status: "unverified",
      snippet: "must not enter the selected projection"
    }
  ],
  review_workflow: null,
  review_decision: null,
  review_resolution: null,
  failure_cause: null,
  query: "must not enter the selected projection",
  unknown_private_field: "ignored"
};

const RESULT = {
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
  query: "ignored",
  unknown_private_field: "ignored"
};

describe("parseRunProjection", () => {
  it("selects only the complete render-safe run projection", () => {
    const projection = parseRunProjection(structuredClone(STATUS));

    expect(projection).toEqual({
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
      evidence: [
        {
          evidence_id: "ev_001",
          source_url: "https://example.com/source",
          source_identity: "https://example.com/source",
          evidence_fingerprint: "sha256:abc",
          citation_status: "cited",
          verification_status: "unverified"
        }
      ],
      review: {
        workflow: null,
        decision: null,
        resolution: null
      },
      currentArtifacts: [],
      failureCause: { kind: "not_applicable" }
    });
    expect("query" in projection).toBe(false);
    expect("unknown_private_field" in projection).toBe(false);
    expect("snippet" in projection.evidence[0]).toBe(false);
    expect(Object.isFrozen(projection)).toBe(true);
    expect(Object.isFrozen(projection.segments)).toBe(true);
    expect(Object.isFrozen(projection.segments[0])).toBe(true);
    expect(Object.isFrozen(projection.evidence)).toBe(true);
    expect(Object.isFrozen(projection.evidence[0])).toBe(true);
    expect(Object.isFrozen(projection.review)).toBe(true);
    expect(Object.isFrozen(projection.currentArtifacts)).toBe(true);
    expect(Object.isFrozen(projection.failureCause)).toBe(true);
  });

  it.each([
    ["run_id", 1],
    ["thread_id", null],
    ["profile_id", false],
    ["execution_status", undefined],
    ["review_status", []],
    ["delivery_status", {}],
    ["state_version", 1.5]
  ])("rejects malformed required run scalar %s", (field, invalidValue) => {
    const value = record(structuredClone(STATUS));
    value[field] = invalidValue;

    expectInvalid(() => parseRunProjection(value));
  });

  it.each([
    ["segment_id", null],
    ["kind", 1],
    ["sequence", 0.5],
    ["attempt", "1"],
    ["status", undefined]
  ])("rejects malformed required segment field %s", (field, invalidValue) => {
    const value = structuredClone(STATUS);
    record(value.segments[0])[field] = invalidValue;

    expectInvalid(() => parseRunProjection(value));
  });

  it.each([
    ["evidence_id", null],
    ["source_url", 1],
    ["source_identity", false],
    ["evidence_fingerprint", undefined],
    ["citation_status", []],
    ["verification_status", {}]
  ])("rejects malformed required Evidence field %s", (field, invalidValue) => {
    const value = structuredClone(STATUS);
    record(value.evidence[0])[field] = invalidValue;

    expectInvalid(() => parseRunProjection(value));
  });

  it("accepts a nullable Evidence source URL", () => {
    const value = structuredClone(STATUS);
    value.evidence[0].source_url = null as unknown as string;

    expect(parseRunProjection(value).evidence[0].source_url).toBeNull();
  });

  it("selects bounded review, verification, publication, and artifact metadata", () => {
    const projection = parseRunProjection(statusWithOptionalProjections());

    expect(projection.review).toEqual({
      workflow: {
        workflow_id: "workflow_001",
        review_id: "review_001",
        review_revision: 2,
        status: "approved",
        decision_id: "decision_001",
        post_review_segment_id: "run_live_001_seg_001",
        attempt_count: 1,
        last_error_code: null,
        created_at: "2026-07-16T08:00:00Z",
        updated_at: "2026-07-16T08:01:00Z"
      },
      decision: {
        decision_id: "decision_001",
        review_id: "review_001",
        review_revision: 2,
        action: "approve",
        reason_recorded: false,
        accepted_state_version: 2,
        created_at: "2026-07-16T08:00:30Z"
      },
      resolution: {
        resolution_id: "resolution_001",
        review_id: "review_001",
        decision_id: "decision_001",
        action: "approve",
        artifact_ids: ["decision-brief.r2.md"],
        created_at: "2026-07-16T08:01:00Z"
      }
    });
    expect(projection.verification).toEqual({
      state_counts: { rejected: 0, verified: 2 },
      origin_counts: { human: 2 },
      snapshot_hash: "sha256:snapshot"
    });
    expect(projection.currentPublication).toEqual({
      publication_id: "publication_001",
      revision: 2,
      status: "ready",
      artifact_ids: ["decision-brief.r2.md"]
    });
    expect(projection.currentArtifacts).toEqual([
      {
        artifact_id: "decision-brief.r2.md",
        kind: "decision_brief_markdown",
        media_type: "text/markdown",
        content_hash: "sha256:artifact",
        created_at: "2026-07-16T08:01:00Z"
      }
    ]);
    expect(projection.failureCause).toEqual({
      kind: "observed",
      schema_version: "dra.run-failure-cause.v1",
      phase: "execution",
      code: "execution_error",
      recorded_at: "2026-07-16T08:02:00Z"
    });
    expect(Object.isFrozen(projection.review.workflow)).toBe(true);
    expect(Object.isFrozen(projection.review.decision)).toBe(true);
    expect(Object.isFrozen(projection.review.resolution)).toBe(true);
    expect(Object.isFrozen(projection.review.resolution?.artifact_ids)).toBe(true);
    expect(Object.isFrozen(projection.verification)).toBe(true);
    expect(Object.isFrozen(projection.verification?.state_counts)).toBe(true);
    expect(Object.isFrozen(projection.verification?.origin_counts)).toBe(true);
    expect(Object.isFrozen(projection.currentPublication)).toBe(true);
    expect(Object.isFrozen(projection.currentPublication?.artifact_ids)).toBe(true);
    expect(Object.isFrozen(projection.currentArtifacts[0])).toBe(true);
  });

  it.each(["review_workflow", "review_decision", "review_resolution"])(
    "rejects malformed review presence field %s",
    (field) => {
      const value = record(structuredClone(STATUS));
      value[field] = [];

      expectInvalid(() => parseRunProjection(value));
    }
  );

  it.each([
    ["workflow_id", null],
    ["review_id", 1],
    ["review_revision", 1.5],
    ["status", false],
    ["decision_id", []],
    ["post_review_segment_id", {}],
    ["attempt_count", "1"],
    ["last_error_code", true],
    ["created_at", undefined],
    ["updated_at", 2]
  ])("rejects malformed selected workflow field %s", (field, invalidValue) => {
    const value = statusWithOptionalProjections();
    record(record(value).review_workflow)[field] = invalidValue;

    expectInvalid(() => parseRunProjection(value));
  });

  it.each([
    ["decision_id", null],
    ["review_id", 1],
    ["review_revision", 1.5],
    ["action", false],
    ["reason_recorded", "false"],
    ["accepted_state_version", "2"],
    ["created_at", undefined]
  ])("rejects malformed selected decision field %s", (field, invalidValue) => {
    const value = statusWithOptionalProjections();
    record(record(value).review_decision)[field] = invalidValue;

    expectInvalid(() => parseRunProjection(value));
  });

  it.each([
    ["resolution_id", null],
    ["review_id", 1],
    ["decision_id", false],
    ["action", undefined],
    ["artifact_ids", [1]],
    ["created_at", {}]
  ])("rejects malformed selected resolution field %s", (field, invalidValue) => {
    const value = statusWithOptionalProjections();
    record(record(value).review_resolution)[field] = invalidValue;

    expectInvalid(() => parseRunProjection(value));
  });

  it.each([
    ["state_counts", "verified", -1],
    ["state_counts", "verified", 1.5],
    ["origin_counts", "human", -1],
    ["origin_counts", "human", 1.5]
  ])("rejects invalid %s count %s=%s", (mapField, key, invalidValue) => {
    const value = statusWithOptionalProjections();
    const verification = record(record(value).verification_summary);
    record(verification[mapField])[key] = invalidValue;

    expectInvalid(() => parseRunProjection(value));
  });

  it.each([
    ["state_counts", null],
    ["origin_counts", []],
    ["snapshot_hash", false]
  ])("rejects malformed verification field %s", (field, invalidValue) => {
    const value = statusWithOptionalProjections();
    record(record(value).verification_summary)[field] = invalidValue;

    expectInvalid(() => parseRunProjection(value));
  });

  it("accepts a nullable verification snapshot hash", () => {
    const value = statusWithOptionalProjections();
    record(record(value).verification_summary).snapshot_hash = null;

    expect(parseRunProjection(value).verification?.snapshot_hash).toBeNull();
  });

  it.each([
    ["publication_id", null],
    ["revision", 1.5],
    ["status", false],
    ["artifact_ids", [1]]
  ])("rejects malformed current publication field %s", (field, invalidValue) => {
    const value = statusWithOptionalProjections();
    record(record(value).current_publication)[field] = invalidValue;

    expectInvalid(() => parseRunProjection(value));
  });

  it.each([
    ["artifact_id", null],
    ["kind", 1],
    ["media_type", false],
    ["content_hash", undefined],
    ["created_at", []]
  ])("rejects malformed current artifact field %s", (field, invalidValue) => {
    const value = statusWithOptionalProjections();
    const artifacts = record(value).current_artifacts as unknown[];
    record(artifacts[0])[field] = invalidValue;

    expectInvalid(() => parseRunProjection(value));
  });

  it.each([
    ["verification_summary", null],
    ["current_publication", []],
    ["current_artifacts", {}]
  ])("rejects malformed optional selected field %s", (field, invalidValue) => {
    const value = statusWithOptionalProjections();
    record(value)[field] = invalidValue;

    expectInvalid(() => parseRunProjection(value));
  });

  it("distinguishes an absent failure cause as unsupported", () => {
    const value = record(structuredClone(STATUS));
    delete value.failure_cause;

    expect(parseRunProjection(value).failureCause).toEqual({ kind: "unsupported" });
  });

  it("distinguishes a null failure cause as not applicable", () => {
    expect(parseRunProjection(structuredClone(STATUS)).failureCause).toEqual({
      kind: "not_applicable"
    });
  });

  it("selects an explicit historical not-observed failure cause", () => {
    const value = record(structuredClone(STATUS));
    value.failure_cause = {
      schema_version: "dra.run-failure-cause.v1",
      observation_status: "not_observed",
      raw_error: "ignored"
    };

    expect(parseRunProjection(value).failureCause).toEqual({
      kind: "not_observed",
      schema_version: "dra.run-failure-cause.v1"
    });
  });

  it.each([
    ["dispatch", "run_dispatch_schedule_failed"],
    ["execution", "run_timeout"],
    ["finalization", "run_finalization_failed"]
  ])("accepts the approved observed failure matrix entry %s/%s", (phase, code) => {
    const value = record(structuredClone(STATUS));
    value.failure_cause = observedFailureCause(phase, code);

    expect(parseRunProjection(value).failureCause).toEqual({
      kind: "observed",
      schema_version: "dra.run-failure-cause.v1",
      phase,
      code,
      recorded_at: "2026-07-16T08:02:00Z"
    });
  });

  it.each([
    ["missing schema version", { observation_status: "not_observed" }],
    [
      "wrong schema version",
      { schema_version: "dra.run-failure-cause.v2", observation_status: "not_observed" }
    ],
    [
      "unknown observation status",
      { schema_version: "dra.run-failure-cause.v1", observation_status: "unknown" }
    ],
    [
      "missing observed phase",
      {
        schema_version: "dra.run-failure-cause.v1",
        observation_status: "observed",
        code: "execution_error",
        recorded_at: "2026-07-16T08:02:00Z"
      }
    ],
    [
      "missing observed code",
      {
        schema_version: "dra.run-failure-cause.v1",
        observation_status: "observed",
        phase: "execution",
        recorded_at: "2026-07-16T08:02:00Z"
      }
    ],
    [
      "missing observed time",
      {
        schema_version: "dra.run-failure-cause.v1",
        observation_status: "observed",
        phase: "execution",
        code: "execution_error"
      }
    ],
    ["unknown phase", observedFailureCause("recovery", "execution_error")],
    ["unknown code", observedFailureCause("execution", "provider_secret")],
    [
      "cross-phase dispatch code",
      observedFailureCause("execution", "run_dispatch_schedule_failed")
    ],
    ["cross-phase execution code", observedFailureCause("finalization", "execution_error")]
  ])("rejects malformed failure cause: %s", (_label, failureCause) => {
    const value = record(structuredClone(STATUS));
    value.failure_cause = failureCause;

    expectInvalid(() => parseRunProjection(value));
  });
});

describe("parseRunResult", () => {
  it("selects and freezes only the canonical result fields", () => {
    const result = parseRunResult(structuredClone(RESULT));

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
    expect("query" in result).toBe(false);
    expect("unknown_private_field" in result).toBe(false);
    expect("local_path" in result.artifact).toBe(false);
    expect(Object.isFrozen(result)).toBe(true);
    expect(Object.isFrozen(result.artifact)).toBe(true);
  });

  it.each([
    ["run_id", null],
    ["execution_status", 1],
    ["delivery_status", false],
    ["artifact", []]
  ])("rejects malformed canonical result field %s", (field, invalidValue) => {
    const value = record(structuredClone(RESULT));
    value[field] = invalidValue;

    expectInvalid(() => parseRunResult(value));
  });

  it.each([
    ["artifact_id", null],
    ["kind", 1],
    ["media_type", false],
    ["content", {}],
    ["content_hash", undefined]
  ])("rejects malformed canonical artifact field %s", (field, invalidValue) => {
    const value = structuredClone(RESULT);
    record(value.artifact)[field] = invalidValue;

    expectInvalid(() => parseRunResult(value));
  });
});

function statusWithOptionalProjections() {
  return {
    ...structuredClone(STATUS),
    review_workflow: {
      workflow_id: "workflow_001",
      run_id: "run_live_001",
      review_id: "review_001",
      review_revision: 2,
      status: "approved",
      decision_id: "decision_001",
      post_review_segment_id: "run_live_001_seg_001",
      attempt_count: 1,
      last_error_code: null,
      created_at: "2026-07-16T08:00:00Z",
      updated_at: "2026-07-16T08:01:00Z",
      lease_owner: "ignored"
    },
    review_decision: {
      decision_id: "decision_001",
      run_id: "run_live_001",
      review_id: "review_001",
      review_revision: 2,
      action: "approve",
      reason_recorded: false,
      accepted_state_version: 2,
      created_at: "2026-07-16T08:00:30Z",
      reason: "ignored",
      actor_fingerprint: "ignored"
    },
    review_resolution: {
      resolution_id: "resolution_001",
      run_id: "run_live_001",
      review_id: "review_001",
      decision_id: "decision_001",
      action: "approve",
      artifact_ids: ["decision-brief.r2.md"],
      created_at: "2026-07-16T08:01:00Z",
      unknown_private_field: "ignored"
    },
    verification_summary: {
      state_counts: { rejected: 0, verified: 2 },
      origin_counts: { human: 2 },
      snapshot_hash: "sha256:snapshot",
      raw_snapshot: "ignored"
    },
    current_publication: {
      publication_id: "publication_001",
      revision: 2,
      status: "ready",
      artifact_ids: ["decision-brief.r2.md"],
      review_id: "ignored"
    },
    current_artifacts: [
      {
        artifact_id: "decision-brief.r2.md",
        kind: "decision_brief_markdown",
        media_type: "text/markdown",
        content_hash: "sha256:artifact",
        created_at: "2026-07-16T08:01:00Z",
        content: "ignored"
      }
    ],
    failure_cause: observedFailureCause("execution", "execution_error")
  };
}

function observedFailureCause(phase: string, code: string) {
  return {
    schema_version: "dra.run-failure-cause.v1",
    observation_status: "observed",
    phase,
    code,
    recorded_at: "2026-07-16T08:02:00Z",
    raw_error: "ignored"
  };
}

function record(value: unknown): Record<string, unknown> {
  return value as Record<string, unknown>;
}

function expectInvalid(parse: () => unknown) {
  expect(parse).toThrowError(/^invalid_response$/);
}
