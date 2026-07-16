import { describe, expect, it } from "vitest";

import type { HealthResponse, RunCreationResponse } from "./apiClient";
import {
  buildLiveConsoleProjection,
  buildStaticConsoleProjection,
  type LiveConsoleProjectionInput,
  type Observation
} from "./consoleProjection";
import type { FailureCauseAvailability, RunProjection, RunResultResponse } from "./runProjection";

const HEALTH: HealthResponse = {
  service: "decision-research-agent",
  status: "ok"
};

const CREATED: RunCreationResponse = {
  run_id: "run_live_alpha",
  segment_id: "segment_live_alpha",
  status: "started",
  thread_id: "thread_live_alpha",
  idempotent_replay: false
};

const LIVE_RUN: RunProjection = {
  run_id: "run_live_alpha",
  thread_id: "thread_live_alpha",
  profile_id: "generic",
  execution_status: "completed",
  review_status: "not_required",
  delivery_status: "ready",
  state_version: 4,
  segments: [
    {
      segment_id: "segment_live_alpha",
      kind: "initial",
      sequence: 0,
      attempt: 1,
      status: "completed"
    }
  ],
  evidence: [
    {
      evidence_id: "evidence_live_alpha",
      source_url: "https://example.com/live-source",
      source_identity: "https://example.com/live-source",
      evidence_fingerprint: "sha256:live-evidence",
      citation_status: "cited",
      verification_status: "unverified"
    }
  ],
  review: {
    workflow: null,
    decision: null,
    resolution: null
  },
  currentPublication: {
    publication_id: "publication_live_alpha",
    revision: 4,
    status: "ready",
    artifact_ids: ["status-artifact-live.md"]
  },
  currentArtifacts: [
    {
      artifact_id: "status-artifact-live.md",
      kind: "research_report_markdown",
      media_type: "text/markdown",
      content_hash: "sha256:status-artifact",
      created_at: "2026-07-16T08:00:00Z"
    }
  ],
  failureCause: { kind: "not_applicable" }
};

const LIVE_RESULT: RunResultResponse = {
  run_id: "run_live_alpha",
  execution_status: "completed",
  delivery_status: "ready",
  artifact: {
    artifact_id: "canonical-live-result.md",
    kind: "research_report_markdown",
    media_type: "text/markdown",
    content: "# Canonical live result\n\nOnly the result response supplies this content.",
    content_hash: "sha256:canonical-live-result"
  }
};

describe("console projection source separation", () => {
  it("preserves the complete deterministic Static Demo screen projection", () => {
    const projection = buildStaticConsoleProjection();

    expect(projection.source).toBe("static");
    expect(projection.summary).toMatchObject({
      service: { kind: "observed", value: "decision-research-agent" },
      health: { kind: "observed", value: "unavailable" },
      mode: "demo data",
      runId: { kind: "observed", value: "run_demo_talent_2026_06_29" }
    });
    expect(projection.command.run).toMatchObject({
      kind: "observed",
      value: {
        runId: "run_demo_talent_2026_06_29",
        threadId: "demo-thread-interview-console",
        profileId: "talent-hiring-signal",
        stateVersion: 17,
        primarySegmentId: {
          kind: "observed",
          value: "run_demo_talent_2026_06_29_seg_final"
        },
        reviewStatus: { kind: "observed", value: "approved" }
      }
    });
    expect(observedValue(projection.lifecycle.entries)).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ category: "lifecycle", label: "evidence_frozen" }),
        expect.objectContaining({ category: "telemetry", label: "result_ready" })
      ])
    );
    expect(observedValue(projection.evidence)).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          evidenceId: "ev_001",
          citedBy: {
            kind: "observed",
            value: ["claim_candidate_signal", "finding_market_signal"]
          },
          verificationStatus: "verified"
        })
      ])
    );
    expect(projection.review).toMatchObject({
      status: { kind: "observed", value: "approved" },
      decisionId: { kind: "observed", value: "decision_demo_approved_001" },
      stateVersion: { kind: "observed", value: 17 },
      idempotency: { kind: "observed", value: "accepted replay-safe decision" }
    });
    expect(observedValue(projection.verification)).toEqual({
      source: "static",
      snapshot: "verification_snapshot_rev_3",
      baselineOrigin: "declared_fixture",
      status: "verified",
      publicationFreshness: "current"
    });
    expect(observedValue(projection.result)).toMatchObject({
      runId: "run_demo_talent_2026_06_29",
      artifact: {
        artifactId: "decision-brief.md",
        mediaType: "text/markdown",
        revision: { kind: "observed", value: "publication_rev_3" },
        contentHash: "sha256:bb64e1d4f8d2a9c7",
        safety: { kind: "observed", value: "hash verified / unsafe content rejected" },
        content: expect.stringContaining("Canonical Decision Brief")
      }
    });
    expect(projection.architecture.nodes).toContain("Application DB Authority");
    expect(projection.architecture.cliGoldenPath).toContain(
      "python tools/decision_research_agent_tool.py run"
    );
    expectDeepFrozen(projection);
  });

  it("returns an empty Live projection with no Static Demo identifiers", () => {
    const projection = buildLiveConsoleProjection(emptyLiveInput());

    expect(projection.source).toBe("live");
    expect(projection.summary).toMatchObject({
      service: { kind: "not_observed" },
      health: { kind: "not_observed" },
      mode: "live backend",
      runId: { kind: "not_observed" }
    });
    expect(projection.command.create).toEqual({ kind: "not_observed" });
    expect(projection.command.run).toEqual({ kind: "not_observed" });
    expect(projection.lifecycle.entries).toEqual({ kind: "not_observed" });
    expect(projection.lifecycle.failureCause).toEqual({ kind: "not_observed" });
    expect(projection.evidence).toEqual({ kind: "not_observed" });
    expect(projection.review.status).toEqual({ kind: "not_observed" });
    expect(projection.verification).toEqual({ kind: "not_observed" });
    expect(projection.result).toEqual({ kind: "not_observed" });
    expect(projection.architecture.cliGoldenPath).toContain(
      '\n  --query "Compare the evidence behind the proposed decision"'
    );
    expect(projection.architecture.cliGoldenPath).not.toMatch(/^\+\s/m);
    expectNoStaticRunIdentifiers(projection);
    expectDeepFrozen(projection);
  });

  it("uses only actual Live run, segment, Evidence, and status values", () => {
    const projection = buildLiveConsoleProjection(
      liveInput({ health: HEALTH, created: CREATED, run: LIVE_RUN, status: "result" })
    );

    expect(projection.source).toBe("live");
    expect(projection.summary).toEqual({
      service: { kind: "observed", value: "decision-research-agent" },
      health: { kind: "observed", value: "ok" },
      mode: "live backend",
      runId: { kind: "observed", value: "run_live_alpha" }
    });
    expect(projection.command.create).toMatchObject({
      kind: "observed",
      value: {
        runId: "run_live_alpha",
        segmentId: "segment_live_alpha",
        status: "started",
        threadId: "thread_live_alpha",
        idempotentReplay: false
      }
    });
    expect(projection.command.run).toMatchObject({
      kind: "observed",
      value: {
        runId: "run_live_alpha",
        threadId: "thread_live_alpha",
        profileId: "generic",
        executionStatus: { kind: "observed", value: "completed" },
        reviewStatus: { kind: "observed", value: "not_required" },
        deliveryStatus: { kind: "observed", value: "ready" },
        stateVersion: 4
      }
    });
    expect(observedValue(projection.lifecycle.entries)).toEqual([
      {
        category: "segment",
        label: "segment_live_alpha",
        segmentKind: "initial",
        status: { kind: "observed", value: "completed" },
        sequence: { kind: "observed", value: 0 },
        attempt: { kind: "observed", value: 1 }
      }
    ]);
    expect(observedValue(projection.evidence)).toEqual([
      {
        evidenceId: "evidence_live_alpha",
        sourceIdentity: "https://example.com/live-source",
        sourceUrl: { kind: "observed", value: "https://example.com/live-source" },
        fingerprint: "sha256:live-evidence",
        citationStatus: { kind: "observed", value: "cited" },
        verificationStatus: "unverified",
        citedBy: { kind: "unsupported" }
      }
    ]);
    expect(projection.review.status).toEqual({
      kind: "observed",
      value: "not_required"
    });
    expect(projection.review.decisionId).toEqual({ kind: "not_applicable" });
    expect(projection.command.publication).toMatchObject({
      kind: "observed",
      value: { publicationId: "publication_live_alpha" }
    });
    expect(observedValue(projection.command.artifacts)).toEqual([
      expect.objectContaining({ artifactId: "status-artifact-live.md" })
    ]);
    expectNoStaticRunIdentifiers(projection);
    expectDeepFrozen(projection);
  });
});

describe("Live observation semantics", () => {
  it("distinguishes an observed empty Evidence ledger from Evidence not yet observed", () => {
    const unobserved = buildLiveConsoleProjection(emptyLiveInput()).evidence;
    const observedEmpty = buildLiveConsoleProjection(
      liveInput({ run: { ...LIVE_RUN, evidence: [] }, status: "terminal" })
    ).evidence;

    expect(unobserved).toEqual({ kind: "not_observed" });
    expect(observedEmpty).toEqual({ kind: "observed", value: [] });
    expect(Object.isFrozen(observedValue(observedEmpty))).toBe(true);
  });

  it("accepts canonical result content only from the supplied RunResultResponse", () => {
    const withoutResult = buildLiveConsoleProjection(
      liveInput({ run: LIVE_RUN, status: "polling" })
    );
    const withResult = buildLiveConsoleProjection(
      liveInput({ run: LIVE_RUN, result: LIVE_RESULT, status: "result" })
    );

    expect(withoutResult.result).toEqual({ kind: "not_observed" });
    expect(JSON.stringify(withoutResult.command.artifacts)).toContain("status-artifact-live.md");
    expect(JSON.stringify(withoutResult)).not.toContain("Canonical live result");
    expect(observedValue(withResult.result)).toEqual({
      runId: "run_live_alpha",
      executionStatus: { kind: "observed", value: "completed" },
      deliveryStatus: { kind: "observed", value: "ready" },
      artifact: {
        artifactId: "canonical-live-result.md",
        kind: { kind: "observed", value: "research_report_markdown" },
        mediaType: "text/markdown",
        contentHash: "sha256:canonical-live-result",
        revision: { kind: "unsupported" },
        safety: { kind: "unsupported" },
        content: "# Canonical live result\n\nOnly the result response supplies this content."
      }
    });
    expect(observedValue(withResult.result).artifact.artifactId).not.toBe(
      "status-artifact-live.md"
    );
  });

  it("marks a terminal non-ready run result as not applicable", () => {
    const projection = buildLiveConsoleProjection(
      liveInput({
        run: { ...LIVE_RUN, delivery_status: "blocked" },
        status: "terminal"
      })
    );

    expect(projection.result).toEqual({ kind: "not_applicable" });
  });

  it.each<[string, FailureCauseAvailability, Observation<unknown>]>([
    ["absent upstream field", { kind: "unsupported" }, { kind: "unsupported" }],
    ["explicit null", { kind: "not_applicable" }, { kind: "not_applicable" }],
    [
      "historical not observed",
      { kind: "not_observed", schema_version: "dra.run-failure-cause.v1" },
      { kind: "not_observed" }
    ],
    [
      "observed bounded cause",
      {
        kind: "observed",
        schema_version: "dra.run-failure-cause.v1",
        phase: "execution",
        code: "execution_error",
        recorded_at: "2026-07-16T08:02:00Z"
      },
      {
        kind: "observed",
        value: {
          schemaVersion: "dra.run-failure-cause.v1",
          phase: "execution",
          code: "execution_error",
          recordedAt: "2026-07-16T08:02:00Z"
        }
      }
    ]
  ])("preserves the distinct failure-cause state for %s", (_label, failureCause, expected) => {
    const projection = buildLiveConsoleProjection(
      liveInput({ run: { ...LIVE_RUN, failureCause }, status: "terminal" })
    );

    expect(projection.lifecycle.failureCause).toEqual(expected);
  });
});

function emptyLiveInput(): LiveConsoleProjectionInput {
  return liveInput({ status: "idle" });
}

function liveInput(
  overrides: Partial<LiveConsoleProjectionInput> = {}
): LiveConsoleProjectionInput {
  return {
    health: undefined,
    created: undefined,
    run: undefined,
    result: undefined,
    status: "idle",
    ...overrides
  };
}

function observedValue<T>(observation: Observation<T>): T {
  if (observation.kind !== "observed") {
    throw new Error(`Expected observed value, received ${observation.kind}.`);
  }
  return observation.value;
}

function expectNoStaticRunIdentifiers(value: unknown) {
  const serialized = JSON.stringify(value);
  for (const forbidden of [
    "run_demo_talent_2026_06_29",
    "ev_001",
    "decision_demo_approved_001",
    "decision-brief.md"
  ]) {
    expect(serialized).not.toContain(forbidden);
  }
}

function expectDeepFrozen(value: unknown): void {
  if (value === null || typeof value !== "object") {
    return;
  }
  expect(Object.isFrozen(value)).toBe(true);
  for (const child of Object.values(value)) {
    expectDeepFrozen(child);
  }
}
