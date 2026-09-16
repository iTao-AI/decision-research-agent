import { describe, expect, it } from "vitest";

import {
  researchBriefFixture,
  validateResearchBriefFixture,
  type ResearchBriefFixture
} from "./demoData";

describe("research brief static fixture", () => {
  it("keeps the first claim semantically bounded and aligned with its exact source excerpt", () => {
    expect(researchBriefFixture.claims[0]).toMatchObject({
      text: "试点先覆盖政策检索与答复草稿，发送前仍需客服审核。",
      excerpt: "第一阶段帮助客服人员定位政策并起草答案。答案由客服人员审核后发送。"
    });
    expect(researchBriefFixture.report.content).toContain(
      "1. 试点先覆盖政策检索与答复草稿，发送前仍需客服审核。Evidence: ev_pilot_scope。"
    );
  });

  it("keeps all claim references, excerpts, and hashes internally consistent", async () => {
    await expect(validateResearchBriefFixture()).resolves.toEqual([]);
  });

  it("rejects a claim that points at a missing Evidence id", async () => {
    const fixture = cloneFixture({
      claims: [{ ...researchBriefFixture.claims[0], evidenceId: "ev_missing" }]
    });

    await expect(validateResearchBriefFixture(fixture)).resolves.toContain(
      "missing evidence id: ev_missing"
    );
  });

  it("rejects an excerpt that is not an exact source substring", async () => {
    const fixture = cloneFixture({
      claims: [{ ...researchBriefFixture.claims[0], excerpt: "这段内容不在来源中。" }]
    });

    await expect(validateResearchBriefFixture(fixture)).resolves.toContain(
      "excerpt mismatch: claim_bounded_assistant"
    );
  });

  it("rejects a report whose bytes no longer match its displayed hash", async () => {
    const fixture = cloneFixture({
      report: {
        ...researchBriefFixture.report,
        content: `${researchBriefFixture.report.content}\n未经授权的附加内容。`
      }
    });

    await expect(validateResearchBriefFixture(fixture)).resolves.toContain("report hash mismatch");
  });
});

function cloneFixture(
  changes: Partial<ResearchBriefFixture> & { claims?: ResearchBriefFixture["claims"] }
): ResearchBriefFixture {
  return {
    ...researchBriefFixture,
    ...changes,
    claims: changes.claims ?? researchBriefFixture.claims,
    sources: changes.sources ?? researchBriefFixture.sources,
    comparison: changes.comparison ?? researchBriefFixture.comparison,
    report: changes.report ?? researchBriefFixture.report
  };
}
