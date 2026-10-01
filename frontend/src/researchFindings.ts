import type { CanonicalArtifactProjection } from "./runProjection";

export const STRUCTURED_RESEARCH_PROFILE = "generic-evidence-report" as const;
export type LiveResearchProfile = "generic" | typeof STRUCTURED_RESEARCH_PROFILE;
export const FINDINGS_ARTIFACT_BYTES_MAX = 1024 * 1024;

export type ResearchQuestion = Readonly<{ question_id: string; text: string }>;
export type BoundSourceReference = Readonly<{
  evidence_id: string; evidence_fingerprint: string; source_url: string; source_identity: string;
  snippet: string; excerpt: string; excerpt_start: number; excerpt_end: number;
}>;
export type BoundFinding = Readonly<{
  finding_id: string; question_id: string; statement: string; references: readonly BoundSourceReference[];
}>;
export type QuestionDisposition = Readonly<{
  question_id: string; status: "candidate_findings" | "unresolved"; reason?: string;
}>;
export type ResearchFindingsReport = Readonly<{
  schema_version: "dra.research-findings.v1"; run_id: string;
  profile_id: typeof STRUCTURED_RESEARCH_PROFILE; profile_version: "1";
  questions: readonly ResearchQuestion[]; findings: readonly BoundFinding[];
  dispositions: readonly QuestionDisposition[]; reported_contradictions: readonly string[];
  limitations: readonly string[];
}>;
export type ResearchFindingsResponse = Readonly<{
  run_id: string; execution_status: "completed"; delivery_status: "ready";
  artifact: CanonicalArtifactProjection; report: ResearchFindingsReport;
}>;

export const FINDINGS_ISSUE_CODES = new Set([
  "candidate_missing", "candidate_too_large", "candidate_invalid_json", "candidate_contract_invalid",
  "unknown_question_id", "duplicate_question_disposition", "question_disposition_missing",
  "question_disposition_conflict", "empty_research_output", "source_url_not_publishable",
  "source_not_observed", "excerpt_not_found", "ambiguous_reference", "reference_binding_failed",
  "artifact_package_too_large"
]);

/** Selected-field consumer validation; delivery and Evidence authority stay on the service. */
export function parseResearchFindings(value: unknown, expectedRunId: string): ResearchFindingsResponse {
  const root = record(value);
  const runId = text(root.run_id, 500);
  if (runId !== expectedRunId || root.execution_status !== "completed" || root.delivery_status !== "ready") invalid();
  const artifact = record(root.artifact);
  if (artifact.artifact_id !== "research-findings.json" || artifact.kind !== "research_findings_json" || artifact.media_type !== "application/json") invalid();
  const content = text(artifact.content);
  if (new TextEncoder().encode(content).byteLength > FINDINGS_ARTIFACT_BYTES_MAX) invalid();
  const report = parseReport(root.report, runId);
  const persisted = parseReport(JSON.parse(content), runId);
  if (JSON.stringify(report) !== JSON.stringify(persisted)) invalid();
  return Object.freeze({
    run_id: runId, execution_status: "completed", delivery_status: "ready", report,
    artifact: Object.freeze({ artifact_id: "research-findings.json", kind: "research_findings_json",
      media_type: "application/json", content, content_hash: fingerprint(artifact.content_hash) })
  });
}

function parseReport(value: unknown, runId: string): ResearchFindingsReport {
  const row = record(value);
  if (row.schema_version !== "dra.research-findings.v1" || row.run_id !== runId ||
      row.profile_id !== STRUCTURED_RESEARCH_PROFILE || row.profile_version !== "1") invalid();
  const questions = list(row.questions, 1, 5, (value) => {
    const question = record(value);
    return Object.freeze({ question_id: questionId(question.question_id), text: text(question.text, 4096) });
  });
  const findings = list(row.findings, 1, 20, (value) => {
    const finding = record(value);
    const findingId = text(finding.finding_id);
    if (!/^f[1-9][0-9]*$/.test(findingId)) invalid();
    return Object.freeze({ finding_id: findingId, question_id: questionId(finding.question_id),
      statement: text(finding.statement, 2000), references: list(finding.references, 1, 10, parseReference) });
  });
  const dispositions = list(row.dispositions, 1, 5, (value): QuestionDisposition => {
    const disposition = record(value);
    const question_id = questionId(disposition.question_id);
    if (disposition.status === "unresolved") {
      return Object.freeze({ question_id, status: "unresolved", reason: text(disposition.reason, 2000) });
    }
    if (disposition.status !== "candidate_findings" || Object.hasOwn(disposition, "reason")) invalid();
    return Object.freeze({ question_id, status: "candidate_findings" });
  });
  unique(questions.map((q) => q.question_id));
  unique(findings.map((f) => f.finding_id));
  unique(dispositions.map((d) => d.question_id));
  const ids = new Set(questions.map((q) => q.question_id));
  if (dispositions.length !== questions.length || findings.some((f) => !ids.has(f.question_id))) invalid();
  for (const disposition of dispositions) {
    if (!ids.has(disposition.question_id) ||
        (disposition.status === "candidate_findings") !== findings.some((f) => f.question_id === disposition.question_id)) invalid();
  }
  return Object.freeze({ schema_version: "dra.research-findings.v1", run_id: runId,
    profile_id: STRUCTURED_RESEARCH_PROFILE, profile_version: "1", questions, findings, dispositions,
    reported_contradictions: list(row.reported_contradictions, 0, 20, (v) => text(v, 2000)),
    limitations: list(row.limitations, 0, 20, (v) => text(v, 2000)) });
}

function parseReference(value: unknown): BoundSourceReference {
  const ref = record(value);
  const snippet = text(ref.snippet);
  const excerpt = text(ref.excerpt, 1000);
  const start = integer(ref.excerpt_start), end = integer(ref.excerpt_end);
  const points = Array.from(snippet);
  if (start < 0 || end <= start || end > points.length || points.slice(start, end).join("") !== excerpt) invalid();
  const first = snippet.indexOf(excerpt);
  if (first < 0 || snippet.indexOf(excerpt, first + 1) >= 0) invalid();
  return Object.freeze({ evidence_id: text(ref.evidence_id, 500), evidence_fingerprint: fingerprint(ref.evidence_fingerprint),
    source_url: text(ref.source_url, 2048), source_identity: text(ref.source_identity, 2048), snippet, excerpt,
    excerpt_start: start, excerpt_end: end });
}

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return invalid();
  return value as Record<string, unknown>;
}
function text(value: unknown, max?: number): string {
  if (typeof value !== "string" || value.trim() === "") return invalid();
  const points = Array.from(value);
  if (max !== undefined && points.length > max) invalid();
  if (points.some((point) => { const cp = point.codePointAt(0)!; return cp >= 0xd800 && cp <= 0xdfff; })) invalid();
  return value;
}
function questionId(value: unknown): string {
  const id = text(value, 64);
  if (!/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(id)) invalid();
  return id;
}
function fingerprint(value: unknown): string {
  const hash = text(value, 64);
  if (!/^[0-9a-f]{64}$/.test(hash)) invalid();
  return hash;
}
function integer(value: unknown): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value)) return invalid();
  return value;
}
function list<T>(value: unknown, min: number, max: number, parse: (v: unknown) => T): readonly T[] {
  if (!Array.isArray(value) || value.length < min || value.length > max) return invalid();
  return Object.freeze(value.map(parse));
}
function unique(ids: readonly string[]) { if (new Set(ids).size !== ids.length) invalid(); }
function invalid(): never { throw new Error("invalid_response"); }
