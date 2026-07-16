import { architectureNodes, demoRun } from "./demoData";
import type { HealthResponse, RunCreationResponse } from "./apiClient";
import type {
  ArtifactMetadataProjection,
  CurrentPublicationProjection,
  FailureCauseAvailability,
  ReviewDecisionProjection,
  ReviewResolutionProjection,
  ReviewWorkflowProjection,
  RunEvidenceProjection,
  RunProjection,
  RunResultResponse,
  RunSegmentProjection,
  VerificationSummaryProjection
} from "./runProjection";

export type Observation<T> =
  | { kind: "observed"; value: T }
  | { kind: "not_observed" }
  | { kind: "not_applicable" }
  | { kind: "unsupported" };

export type SummaryProjection = Readonly<{
  service: Observation<string>;
  health: Observation<string>;
  mode: "demo data" | "live backend";
  runId: Observation<string>;
}>;

export type CreateReceiptView = Readonly<{
  runId: string;
  segmentId: string;
  status: string;
  threadId: string;
  idempotentReplay: boolean;
}>;

export type RunView = Readonly<{
  runId: string;
  threadId: string;
  profileId: string;
  stateVersion: number;
  primarySegmentId: Observation<string>;
  executionStatus: Observation<string>;
  reviewStatus: Observation<string>;
  deliveryStatus: Observation<string>;
}>;

export type PublicationView = Readonly<{
  publicationId: string;
  revision: number;
  status: string;
  artifactIds: readonly string[];
}>;

export type ArtifactMetadataView = Readonly<{
  artifactId: string;
  kind: string;
  mediaType: string;
  contentHash: string;
  createdAt: string;
}>;

export type CommandProjection = Readonly<{
  create: Observation<CreateReceiptView>;
  run: Observation<RunView>;
  publication: Observation<PublicationView>;
  artifacts: Observation<readonly ArtifactMetadataView[]>;
}>;

export type LifecycleEntryView = Readonly<{
  category: "lifecycle" | "telemetry" | "segment";
  label: string;
  segmentKind?: string;
  status: Observation<string>;
  sequence: Observation<number>;
  attempt: Observation<number>;
}>;

export type FailureCauseView = Readonly<{
  schemaVersion: "dra.run-failure-cause.v1";
  phase: string;
  code: string;
  recordedAt: string;
}>;

export type LifecycleProjection = Readonly<{
  kind: "event_history" | "state_projection";
  run: Observation<RunView>;
  entries: Observation<readonly LifecycleEntryView[]>;
  failureCause: Observation<FailureCauseView>;
}>;

export type EvidenceView = Readonly<{
  evidenceId: string;
  sourceIdentity: string;
  sourceUrl: Observation<string>;
  fingerprint: string;
  citationStatus: Observation<string>;
  verificationStatus: string;
  citedBy: Observation<readonly string[]>;
}>;

export type ReviewView = Readonly<{
  status: Observation<string>;
  decisionId: Observation<string>;
  stateVersion: Observation<number>;
  idempotency: Observation<string>;
  workflow: Observation<ReviewWorkflowProjection>;
  decision: Observation<ReviewDecisionProjection>;
  resolution: Observation<ReviewResolutionProjection>;
}>;

export type StaticVerificationView = Readonly<{
  source: "static";
  snapshot: string;
  baselineOrigin: string;
  status: string;
  publicationFreshness: string;
}>;

export type LiveVerificationView = Readonly<{
  source: "live";
  stateCounts: Readonly<Record<string, number>>;
  originCounts: Readonly<Record<string, number>>;
  snapshotHash: string | null;
}>;

export type VerificationView = StaticVerificationView | LiveVerificationView;

export type ResultArtifactView = Readonly<{
  artifactId: string;
  kind: Observation<string>;
  mediaType: string;
  contentHash: string;
  revision: Observation<string>;
  safety: Observation<string>;
  content: string;
}>;

export type ResultView = Readonly<{
  runId: string;
  executionStatus: Observation<string>;
  deliveryStatus: Observation<string>;
  artifact: ResultArtifactView;
}>;

export type ArchitectureReferenceProjection = Readonly<{
  referenceOnly: true;
  nodes: readonly string[];
  cliGoldenPath: string;
}>;

export type ConsoleProjection = Readonly<{
  source: "static" | "live";
  summary: SummaryProjection;
  command: CommandProjection;
  lifecycle: LifecycleProjection;
  evidence: Observation<readonly EvidenceView[]>;
  review: ReviewView;
  verification: Observation<VerificationView>;
  result: Observation<ResultView>;
  architecture: ArchitectureReferenceProjection;
}>;

export type LiveConsoleProjectionInput = Readonly<{
  health: HealthResponse | undefined;
  created: RunCreationResponse | undefined;
  run: RunProjection | undefined;
  result: RunResultResponse | undefined;
  status: string;
}>;

const LIVE_CLI_GOLDEN_PATH = [
  "python tools/decision_research_agent_tool.py run \\",
  '  --query "Compare the evidence behind the proposed decision" \\',
  "  --wait \\",
  "  --result"
].join("\n");

export function buildStaticConsoleProjection(): ConsoleProjection {
  const run = freezeRunView({
    runId: demoRun.runId,
    threadId: demoRun.threadId,
    profileId: demoRun.profileId,
    stateVersion: demoRun.stateVersion,
    primarySegmentId: observed(demoRun.segmentId),
    executionStatus: notObserved(),
    reviewStatus: observed(demoRun.review.status),
    deliveryStatus: notObserved()
  });
  const lifecycleEntries = freezeArray([
    ...demoRun.lifecycle.map((label) =>
      freezeLifecycleEntry({
        category: "lifecycle",
        label,
        status: observed(label),
        sequence: unsupported(),
        attempt: unsupported()
      })
    ),
    ...demoRun.telemetry.map((label) =>
      freezeLifecycleEntry({
        category: "telemetry",
        label,
        status: unsupported(),
        sequence: unsupported(),
        attempt: unsupported()
      })
    )
  ]);
  const evidence = freezeArray(
    demoRun.evidence.map((entry) =>
      Object.freeze({
        evidenceId: entry.id,
        sourceIdentity: entry.source,
        sourceUrl: unsupported<string>(),
        fingerprint: entry.fingerprint,
        citationStatus: unsupported<string>(),
        verificationStatus: entry.verification,
        citedBy: observed(freezeArray([...entry.citedBy]))
      })
    )
  );
  const verification = Object.freeze({
    source: "static" as const,
    snapshot: demoRun.verification.snapshot,
    baselineOrigin: demoRun.verification.baselineOrigin,
    status: demoRun.verification.status,
    publicationFreshness: demoRun.verification.publicationFreshness
  });
  const result = Object.freeze({
    runId: demoRun.runId,
    executionStatus: notObserved<string>(),
    deliveryStatus: notObserved<string>(),
    artifact: Object.freeze({
      artifactId: demoRun.artifact.id,
      kind: unsupported<string>(),
      mediaType: demoRun.artifact.mediaType,
      contentHash: demoRun.artifact.contentHash,
      revision: observed(demoRun.artifact.revision),
      safety: observed(demoRun.artifact.safety),
      content: demoRun.resultMarkdown
    })
  });

  return Object.freeze({
    source: "static",
    summary: Object.freeze({
      service: observed(demoRun.service),
      health: observed(demoRun.health),
      mode: demoRun.mode as "demo data",
      runId: observed(demoRun.runId)
    }),
    command: Object.freeze({
      create: notApplicable<CreateReceiptView>(),
      run: observed(run),
      publication: unsupported<PublicationView>(),
      artifacts: unsupported<readonly ArtifactMetadataView[]>()
    }),
    lifecycle: Object.freeze({
      kind: "event_history",
      run: observed(run),
      entries: observed(lifecycleEntries),
      failureCause: unsupported<FailureCauseView>()
    }),
    evidence: observed(evidence),
    review: Object.freeze({
      status: observed(demoRun.review.status),
      decisionId: observed(demoRun.review.decisionId),
      stateVersion: observed(demoRun.review.stateVersion),
      idempotency: observed(demoRun.review.idempotency),
      workflow: unsupported<ReviewWorkflowProjection>(),
      decision: unsupported<ReviewDecisionProjection>(),
      resolution: unsupported<ReviewResolutionProjection>()
    }),
    verification: observed(verification),
    result: observed(result),
    architecture: buildArchitectureReference(demoRun.cliGoldenPath)
  });
}

export function buildLiveConsoleProjection(
  input: LiveConsoleProjectionInput
): ConsoleProjection {
  const run = input.run === undefined ? undefined : buildLiveRunView(input.run, input.created);
  const runObservation = run === undefined ? notObserved<RunView>() : observed(run);
  const runId = input.run?.run_id ?? input.created?.run_id ?? input.result?.run_id;

  return Object.freeze({
    source: "live",
    summary: Object.freeze({
      service:
        input.health === undefined ? notObserved<string>() : observed(input.health.service),
      health:
        input.health === undefined ? notObserved<string>() : observed(input.health.status),
      mode: "live backend",
      runId: runId === undefined ? notObserved<string>() : observed(runId)
    }),
    command: Object.freeze({
      create:
        input.created === undefined
          ? notObserved<CreateReceiptView>()
          : observed(copyCreateReceipt(input.created)),
      run: runObservation,
      publication: buildPublicationObservation(input.run),
      artifacts: buildArtifactObservation(input.run)
    }),
    lifecycle: Object.freeze({
      kind: "state_projection",
      run: runObservation,
      entries:
        input.run === undefined
          ? notObserved<readonly LifecycleEntryView[]>()
          : observed(freezeArray(input.run.segments.map(copySegmentEntry))),
      failureCause:
        input.run === undefined
          ? notObserved<FailureCauseView>()
          : projectFailureCause(input.run.failureCause)
    }),
    evidence:
      input.run === undefined
        ? notObserved<readonly EvidenceView[]>()
        : observed(freezeArray(input.run.evidence.map(copyEvidence))),
    review: buildLiveReview(input.run),
    verification: buildVerificationObservation(input.run),
    result: buildResultObservation(input),
    architecture: buildArchitectureReference(LIVE_CLI_GOLDEN_PATH)
  });
}

function buildLiveRunView(
  run: RunProjection,
  created: RunCreationResponse | undefined
): RunView {
  return freezeRunView({
    runId: run.run_id,
    threadId: run.thread_id,
    profileId: run.profile_id,
    stateVersion: run.state_version,
    primarySegmentId:
      created === undefined ? notObserved<string>() : observed(created.segment_id),
    executionStatus: observed(run.execution_status),
    reviewStatus: observed(run.review_status),
    deliveryStatus: observed(run.delivery_status)
  });
}

function freezeRunView(run: RunView): RunView {
  return Object.freeze({ ...run });
}

function copyCreateReceipt(created: RunCreationResponse): CreateReceiptView {
  return Object.freeze({
    runId: created.run_id,
    segmentId: created.segment_id,
    status: created.status,
    threadId: created.thread_id,
    idempotentReplay: created.idempotent_replay
  });
}

function buildPublicationObservation(
  run: RunProjection | undefined
): Observation<PublicationView> {
  if (run === undefined || run.currentPublication === undefined) {
    return notObserved();
  }
  return observed(copyPublication(run.currentPublication));
}

function copyPublication(publication: CurrentPublicationProjection): PublicationView {
  return Object.freeze({
    publicationId: publication.publication_id,
    revision: publication.revision,
    status: publication.status,
    artifactIds: freezeArray([...publication.artifact_ids])
  });
}

function buildArtifactObservation(
  run: RunProjection | undefined
): Observation<readonly ArtifactMetadataView[]> {
  if (run === undefined || run.currentArtifacts === undefined) {
    return notObserved();
  }
  return observed(freezeArray(run.currentArtifacts.map(copyArtifactMetadata)));
}

function copyArtifactMetadata(artifact: ArtifactMetadataProjection): ArtifactMetadataView {
  return Object.freeze({
    artifactId: artifact.artifact_id,
    kind: artifact.kind,
    mediaType: artifact.media_type,
    contentHash: artifact.content_hash,
    createdAt: artifact.created_at
  });
}

function copySegmentEntry(segment: RunSegmentProjection): LifecycleEntryView {
  return freezeLifecycleEntry({
    category: "segment",
    label: segment.segment_id,
    segmentKind: segment.kind,
    status: observed(segment.status),
    sequence: observed(segment.sequence),
    attempt: observed(segment.attempt)
  });
}

function freezeLifecycleEntry(entry: LifecycleEntryView): LifecycleEntryView {
  return Object.freeze({ ...entry });
}

function copyEvidence(evidence: RunEvidenceProjection): EvidenceView {
  return Object.freeze({
    evidenceId: evidence.evidence_id,
    sourceIdentity: evidence.source_identity,
    sourceUrl:
      evidence.source_url === null ? notApplicable<string>() : observed(evidence.source_url),
    fingerprint: evidence.evidence_fingerprint,
    citationStatus: observed(evidence.citation_status),
    verificationStatus: evidence.verification_status,
    citedBy: unsupported<readonly string[]>()
  });
}

function buildLiveReview(run: RunProjection | undefined): ReviewView {
  if (run === undefined) {
    return Object.freeze({
      status: notObserved<string>(),
      decisionId: notObserved<string>(),
      stateVersion: notObserved<number>(),
      idempotency: unsupported<string>(),
      workflow: notObserved<ReviewWorkflowProjection>(),
      decision: notObserved<ReviewDecisionProjection>(),
      resolution: notObserved<ReviewResolutionProjection>()
    });
  }

  const absentReview = <T>() =>
    run.review_status === "not_required" ? notApplicable<T>() : notObserved<T>();
  const workflow =
    run.review.workflow === null
      ? absentReview<ReviewWorkflowProjection>()
      : observed(copyReviewWorkflow(run.review.workflow));
  const decision =
    run.review.decision === null
      ? absentReview<ReviewDecisionProjection>()
      : observed(copyReviewDecision(run.review.decision));
  const resolution =
    run.review.resolution === null
      ? absentReview<ReviewResolutionProjection>()
      : observed(copyReviewResolution(run.review.resolution));

  return Object.freeze({
    status: observed(run.review_status),
    decisionId:
      run.review.decision === null
        ? absentReview<string>()
        : observed(run.review.decision.decision_id),
    stateVersion: observed(run.state_version),
    idempotency: unsupported<string>(),
    workflow,
    decision,
    resolution
  });
}

function copyReviewWorkflow(workflow: ReviewWorkflowProjection): ReviewWorkflowProjection {
  return Object.freeze({ ...workflow });
}

function copyReviewDecision(decision: ReviewDecisionProjection): ReviewDecisionProjection {
  return Object.freeze({ ...decision });
}

function copyReviewResolution(resolution: ReviewResolutionProjection): ReviewResolutionProjection {
  return Object.freeze({
    ...resolution,
    artifact_ids: freezeArray([...resolution.artifact_ids])
  });
}

function buildVerificationObservation(
  run: RunProjection | undefined
): Observation<VerificationView> {
  if (run?.verification === undefined) {
    return notObserved();
  }
  return observed(copyVerification(run.verification));
}

function copyVerification(verification: VerificationSummaryProjection): LiveVerificationView {
  return Object.freeze({
    source: "live",
    stateCounts: freezeRecord(verification.state_counts),
    originCounts: freezeRecord(verification.origin_counts),
    snapshotHash: verification.snapshot_hash
  });
}

function buildResultObservation(input: LiveConsoleProjectionInput): Observation<ResultView> {
  if (input.result !== undefined) {
    return observed(
      Object.freeze({
        runId: input.result.run_id,
        executionStatus: observed(input.result.execution_status),
        deliveryStatus: observed(input.result.delivery_status),
        artifact: Object.freeze({
          artifactId: input.result.artifact.artifact_id,
          kind: observed(input.result.artifact.kind),
          mediaType: input.result.artifact.media_type,
          contentHash: input.result.artifact.content_hash,
          revision: unsupported<string>(),
          safety: unsupported<string>(),
          content: input.result.artifact.content
        })
      })
    );
  }
  return input.status === "terminal" ? notApplicable() : notObserved();
}

function projectFailureCause(
  failureCause: FailureCauseAvailability
): Observation<FailureCauseView> {
  switch (failureCause.kind) {
    case "unsupported":
      return unsupported();
    case "not_applicable":
      return notApplicable();
    case "not_observed":
      return notObserved();
    case "observed":
      return observed(
        Object.freeze({
          schemaVersion: failureCause.schema_version,
          phase: failureCause.phase,
          code: failureCause.code,
          recordedAt: failureCause.recorded_at
        })
      );
  }
}

function buildArchitectureReference(cliGoldenPath: string): ArchitectureReferenceProjection {
  return Object.freeze({
    referenceOnly: true,
    nodes: freezeArray([...architectureNodes]),
    cliGoldenPath
  });
}

function observed<T>(value: T): Observation<T> {
  return Object.freeze({ kind: "observed", value });
}

function notObserved<T>(): Observation<T> {
  return Object.freeze({ kind: "not_observed" });
}

function notApplicable<T>(): Observation<T> {
  return Object.freeze({ kind: "not_applicable" });
}

function unsupported<T>(): Observation<T> {
  return Object.freeze({ kind: "unsupported" });
}

function freezeArray<T>(values: T[]): readonly T[] {
  return Object.freeze(values);
}

function freezeRecord(value: Readonly<Record<string, number>>): Readonly<Record<string, number>> {
  return Object.freeze({ ...value });
}
