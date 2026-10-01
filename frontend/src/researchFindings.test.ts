import { afterEach, describe, expect, it, vi } from "vitest";
import * as client from "./apiClient";
import { findingsResponse } from "./test/researchFindingsFixture";
import { structuredRun } from "./test/researchFindingsFixture";

afterEach(() => vi.unstubAllGlobals());

function serve(value: unknown) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(value))));
}
function refreshContent(value: ReturnType<typeof findingsResponse>) {
  value.artifact.content = JSON.stringify(value.report);
}

describe("canonical findings consumer", () => {
  it("selects canonical fields with Python code-point offsets and ignores unselected extensions", async () => {
    const value = findingsResponse();
    serve({ ...value, internal_candidate: "not rendered" });
    const response = await client.getFindings("http://127.0.0.1:8000", "run_structured");
    expect(response.report.findings[0].references[0].excerpt).toBe("😀精确片段");
    expect(response).not.toHaveProperty("internal_candidate");
  });

  it("accepts a full 1000-code-point emoji excerpt and a longer persisted snippet", async () => {
    const value = findingsResponse();
    Object.assign(value.report.findings[0].references[0], {
      snippet: `前${"😀".repeat(1000)}${"余".repeat(5000)}`,
      excerpt: "😀".repeat(1000), excerpt_start: 1, excerpt_end: 1001
    });
    refreshContent(value); serve(value);
    expect((await client.getFindings("http://127.0.0.1:8000", "run_structured")).report.findings[0].references[0].snippet.endsWith("余".repeat(5000))).toBe(true);
  });

  it.each([
    ["foreign run", (v: ReturnType<typeof findingsResponse>) => { v.report.run_id = "foreign"; }],
    ["wrong profile", (v: ReturnType<typeof findingsResponse>) => { v.report.profile_id = "generic"; }],
    ["wrong version", (v: ReturnType<typeof findingsResponse>) => { v.report.profile_version = "2"; }],
    ["not ready", (v: ReturnType<typeof findingsResponse>) => { v.delivery_status = "blocked"; }],
    ["wrong artifact", (v: ReturnType<typeof findingsResponse>) => { v.artifact.kind = "other"; }],
    ["invalid hash", (v: ReturnType<typeof findingsResponse>) => { v.artifact.content_hash = "x"; }],
    ["UTF16 offsets", (v: ReturnType<typeof findingsResponse>) => { v.report.findings[0].references[0].excerpt_end = 7; }],
    ["ambiguous quote", (v: ReturnType<typeof findingsResponse>) => { v.report.findings[0].references[0].snippet += "😀精确片段"; }],
    ["duplicate question", (v: ReturnType<typeof findingsResponse>) => { v.report.questions.push(v.report.questions[0]); }],
    ["duplicate finding", (v: ReturnType<typeof findingsResponse>) => { v.report.findings.push(v.report.findings[0]); }],
    ["duplicate disposition", (v: ReturnType<typeof findingsResponse>) => { v.report.dispositions.push(v.report.dispositions[0]); }],
    ["missing disposition", (v: ReturnType<typeof findingsResponse>) => { v.report.dispositions.pop(); }],
    ["unknown question", (v: ReturnType<typeof findingsResponse>) => { v.report.findings[0].question_id = "q9"; }],
    ["empty findings", (v: ReturnType<typeof findingsResponse>) => { v.report.findings = []; }],
    ["bad disposition", (v: ReturnType<typeof findingsResponse>) => { v.report.dispositions[0].status = "unresolved"; }],
    ["oversized excerpt", (v: ReturnType<typeof findingsResponse>) => { v.report.findings[0].references[0].excerpt = "😀".repeat(1001); }],
    ["invalid fingerprint", (v: ReturnType<typeof findingsResponse>) => { v.report.findings[0].references[0].evidence_fingerprint = "A".repeat(64); }],
    ["empty references", (v: ReturnType<typeof findingsResponse>) => { v.report.findings[0].references = []; }],
    ["too many references", (v: ReturnType<typeof findingsResponse>) => { v.report.findings[0].references = Array(11).fill(v.report.findings[0].references[0]); }],
    ["too many findings", (v: ReturnType<typeof findingsResponse>) => { v.report.findings = Array(21).fill(v.report.findings[0]); }],
    ["oversized question", (v: ReturnType<typeof findingsResponse>) => { v.report.questions[0].text = "😀".repeat(4097); }],
    ["oversized statement", (v: ReturnType<typeof findingsResponse>) => { v.report.findings[0].statement = "😀".repeat(2001); }],
    ["oversized URL", (v: ReturnType<typeof findingsResponse>) => { v.report.findings[0].references[0].source_url = "x".repeat(2049); }],
    ["oversized identity", (v: ReturnType<typeof findingsResponse>) => { v.report.findings[0].references[0].evidence_id = "x".repeat(501); }],
    ["too many limitations", (v: ReturnType<typeof findingsResponse>) => { v.report.limitations = Array(21).fill("limit"); }],
    ["surrogate", (v: ReturnType<typeof findingsResponse>) => { v.report.findings[0].statement = "\ud800"; }],
    ["artifact byte bound", (v: ReturnType<typeof findingsResponse>) => { v.report.findings[0].references[0].snippet += "😀".repeat(262144); }]
  ])("rejects %s with a bounded client error", async (_name, mutate) => {
    const value = findingsResponse(); mutate(value); refreshContent(value); serve(value);
    await expect(client.getFindings("http://127.0.0.1:8000", "run_structured")).rejects.toMatchObject({ details: { code: "invalid_response" } });
  });

  it("rejects typed report disagreement with the persisted content", async () => {
    const value = findingsResponse(); value.report.findings[0].statement = "replacement"; serve(value);
    await expect(client.getFindings("http://127.0.0.1:8000", "run_structured")).rejects.toMatchObject({ details: { code: "invalid_response" } });
  });

  it("freezes the nested structured scope and keeps exact query on keyed transport", async () => {
    const intent = client.createRunIntent("  查询\n原文  ", () => "uuid", "generic-evidence-report");
    expect(intent.payload).toMatchObject({ query: "  查询\n原文  ", profile_id: "generic-evidence-report",
      scope: { questions: [{ question_id: "q1", text: "  查询\n原文  " }] } });
    expect(Object.isFrozen(intent.payload.scope.questions)).toBe(true);
    expect(Object.isFrozen(intent.payload.scope.questions?.[0])).toBe(true);
  });

  it("accepts the exact 1 MiB UTF-8 artifact boundary without an invented snippet or finding-ID bound", async () => {
    const value = findingsResponse();
    value.report.findings[0].finding_id = `f1${"0".repeat(80)}`;
    const before = new TextEncoder().encode(JSON.stringify(value.report)).byteLength;
    value.report.findings[0].references[0].snippet += "x".repeat(1048576 - before);
    refreshContent(value); serve(value);
    expect(new TextEncoder().encode(value.artifact.content).byteLength).toBe(1048576);
    expect((await client.getFindings("http://127.0.0.1:8000", "run_structured")).report.findings).toHaveLength(1);
  });

  it("bounds malformed oversized service error text without exposing it", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
      code: "run_result_unavailable", problem: "private".repeat(10000), cause: "x", fix: "x", retryable: false
    }), { status: 409 })));
    await expect(client.getFindings("http://127.0.0.1:8000", "run_structured")).rejects.toMatchObject({
      details: { code: "invalid_response", problem: "Backend response could not be rendered safely." }
    });
  });

  it("accepts backend-full Unicode question and statement bounds", async () => {
    const value = findingsResponse();
    value.report.questions[0].text = "😀".repeat(4096);
    value.report.findings[0].statement = "😀".repeat(2000);
    refreshContent(value); serve(value);
    const parsed = await client.getFindings("http://127.0.0.1:8000", "run_structured");
    expect(Array.from(parsed.report.questions[0].text)).toHaveLength(4096);
    expect(Array.from(parsed.report.findings[0].statement)).toHaveLength(2000);
  });

  it.each([
    { findings_issues: ["raw_internal_exception"] },
    { findings_issues: Array(21).fill("candidate_missing") },
    { findings_outcome: { requested_question_count: 1, covered_question_count: 1, unresolved_question_count: 1, reference_binding_failure_count: 0 } },
    { findings_outcome: { requested_question_count: 1, covered_question_count: 0, unresolved_question_count: 1, reference_binding_failure_count: 201 } }
  ])("rejects malformed optional diagnostic selected fields", async (diagnostics) => {
    serve({ ...structuredRun(), ...diagnostics });
    await expect(client.getRun("http://127.0.0.1:8000", "run_structured")).rejects.toMatchObject({ details: { code: "invalid_response" } });
  });
});
