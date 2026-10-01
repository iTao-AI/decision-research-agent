export function findingsResponse(runId = "run_structured") {
  const report = {
    schema_version: "dra.research-findings.v1",
    run_id: runId,
    profile_id: "generic-evidence-report",
    profile_version: "1",
    questions: [{ question_id: "q1", text: "研究问题" }, { question_id: "q2", text: "未解决问题" }],
    findings: [{
      finding_id: "f1", question_id: "q1", statement: "来源绑定的候选结论",
      references: [{ evidence_id: "e1", evidence_fingerprint: "a".repeat(64),
        source_url: "https://example.com/source", source_identity: "https://example.com/source",
        snippet: "前😀精确片段后", excerpt: "😀精确片段", excerpt_start: 1, excerpt_end: 6 }]
    }],
    dispositions: [{ question_id: "q1", status: "candidate_findings" },
      { question_id: "q2", status: "unresolved", reason: "证据不足" }],
    reported_contradictions: ["两个来源的更新时间存在矛盾"], limitations: ["片段绑定不证明结论真实"]
  };
  return { run_id: runId, execution_status: "completed", delivery_status: "ready",
    artifact: { artifact_id: "research-findings.json", kind: "research_findings_json",
      media_type: "application/json", content: JSON.stringify(report), content_hash: "b".repeat(64) }, report };
}

export function structuredRun(runId = "run_structured", delivery = "ready") {
  return { run_id: runId, thread_id: "existing-thread", profile_id: "generic-evidence-report",
    execution_status: "completed", delivery_status: delivery, review_status: "not_required",
    state_version: 1, segments: [], evidence: [], review_workflow: null,
    review_decision: null, review_resolution: null, failure_cause: null };
}

export function markdownResult(runId = "run_structured") {
  return { run_id: runId, execution_status: "completed", delivery_status: "ready",
    artifact: { artifact_id: "research-report.md", kind: "research_findings_markdown",
      media_type: "text/markdown", content: "# Canonical report", content_hash: "c".repeat(64) } };
}
