export type DemoSourceFixture = Readonly<{
  evidenceId: string;
  title: string;
  content: string;
  fingerprint: string;
}>;

export type DemoClaimFixture = Readonly<{
  claimId: string;
  text: string;
  evidenceId: string;
  excerpt: string;
}>;

export type DemoComparisonRow = Readonly<{
  option: string;
  integration: string;
  humanDecision: string;
  evaluation: string;
}>;

export type ResearchBriefFixture = Readonly<{
  caseId: string;
  question: string;
  disclosure: string;
  recommendation: string;
  recommendationDetail: string;
  comparison: readonly DemoComparisonRow[];
  claims: readonly DemoClaimFixture[];
  sources: readonly DemoSourceFixture[];
  report: Readonly<{
    artifactId: string;
    mediaType: "text/markdown";
    content: string;
    contentHash: string;
  }>;
}>;

const question = "客服团队应该先试点内部知识助手，还是直接让 Agent 自动处理退款？";

export const researchBriefFixture: ResearchBriefFixture = {
  caseId: "customer-support-refund-pilot-v1",
  question,
  disclosure: "以下是本地静态演示案例，不代表真实客户试点、模型评测或生产收益。",
  recommendation: "先试点内部知识助手",
  recommendationDetail:
    "让客服人员检索已批准的政策材料、生成带依据的草稿，再由授权工作人员审核后发送。当前材料支持这个受控范围，但不支持直接承诺 Agent 自动写入退款。",
  comparison: [
    {
      option: "内部知识助手",
      integration: "可以读取已批准的政策材料和订单信息。",
      humanDecision: "客服人员审核草稿后发送。",
      evaluation: "可评估政策检索、草稿可审查性和复核流程。"
    },
    {
      option: "Agent 自动处理退款",
      integration: "生产环境退款写入集成尚未获批准或验证。",
      humanDecision: "退款决定仍需要授权工作人员。",
      evaluation: "无法在当前证据边界内承诺自动退款。"
    }
  ],
  claims: [
    {
      claimId: "claim_bounded_assistant",
      text: "现有读取能力支持先做带政策依据的客服草稿助手。",
      evidenceId: "ev_pilot_scope",
      excerpt: "第一阶段帮助客服人员定位政策并起草答案。"
    },
    {
      claimId: "claim_refund_write_unconfirmed",
      text: "退款写入接入尚未被批准或验证，因此不能承诺 Agent 自动退款。",
      evidenceId: "ev_system_access",
      excerpt: "生产环境退款写入集成尚未获批准或验证。"
    },
    {
      claimId: "claim_staff_approval",
      text: "退款决定保留授权工作人员审批，政策不明或证据缺失时升级。",
      evidenceId: "ev_refund_policy",
      excerpt: "退款决定需要授权工作人员。政策不明确或证据缺失时，必须升级处理。"
    }
  ],
  sources: [
    {
      evidenceId: "ev_pilot_scope",
      title: "试点需求记录",
      content:
        "第一阶段帮助客服人员定位政策并起草答案。答案由客服人员审核后发送。本记录没有提供已测量的业务改善数据。",
      fingerprint: "sha256:30ebb4ebe276a9b2971a77c301892093f714d6883cd1a82bcbd2e57d21554319"
    },
    {
      evidenceId: "ev_system_access",
      title: "系统接入清单",
      content:
        "试点可以读取已批准的政策材料和订单信息。生产环境退款写入集成尚未获批准或验证。",
      fingerprint: "sha256:8e974c4d5a84914a95f641b243186e9d678d4a1dc8375628715040401a6dccdc"
    },
    {
      evidenceId: "ev_refund_policy",
      title: "退款处理规则",
      content:
        "退款决定需要授权工作人员。政策不明确或证据缺失时，必须升级处理。",
      fingerprint: "sha256:6f64a4d48abc9ef419e5d4caca8488ceb194434eead63a5b6628d76d544380df"
    }
  ],
  report: {
    artifactId: "customer-support-refund-pilot-decision-brief.md",
    mediaType: "text/markdown",
    content: `# 客服退款自动化试点决策简报

## 研究问题

客服团队应该先试点内部知识助手，还是直接让 Agent 自动处理退款？

## 研究结论

先试点内部知识助手。第一阶段让客服人员检索已批准的政策材料、生成带依据的草稿，再由授权工作人员审核后发送。当前材料支持这个受控范围，但不支持直接承诺 Agent 自动写入退款。

## 比较依据

- 当前接入：可以读取已批准的政策材料和订单信息，但生产环境退款写入集成尚未获批准或验证。
- 人工决策：退款决定需要授权工作人员；政策不明确或证据缺失时必须升级处理。
- 可评估内容：本次试点可以评估政策检索、草稿可审查性和人工复核流程。

## 支持性发现

1. 现有读取能力支持先做带政策依据的客服草稿助手。Evidence: ev_pilot_scope。
2. 退款写入接入尚未被批准或验证，因此不能承诺 Agent 自动退款。Evidence: ev_system_access。
3. 退款决定保留授权工作人员审批，政策不明或证据缺失时升级。Evidence: ev_refund_policy。

## 尚待测量

节省时间、采用率和其他业务改善仍待测量。本静态案例没有提供流量、ROI、客户采用率或模型准确率数据。
`,
    contentHash: "sha256:35a6d30a26ea65ae940c227177fd901862920e7b7e5853fd098590cdeb747766"
  }
};

export const demoRun = {
  service: "decision-research-agent",
  mode: "demo data",
  health: "unavailable",
  runId: "run_demo_support_refund_normal",
  threadId: "demo-thread-support-refund",
  segmentId: "run_demo_support_refund_normal_seg_final",
  stateVersion: 17,
  profileId: "generic-research",
  lifecycle: [
    "created",
    "running",
    "evidence_frozen",
    "review_required",
    "approved",
    "published",
    "delivered"
  ],
  telemetry: [
    "session_created",
    "plan_recorded",
    "tool_start: declared_fixture_read",
    "evidence_snapshot_frozen",
    "result_ready"
  ],
  evidence: researchBriefFixture.sources.map((source) => ({
    id: source.evidenceId,
    source: source.title,
    sourceTitle: source.title,
    sourceContent: source.content,
    fingerprint: source.fingerprint,
    citedBy: researchBriefFixture.claims
      .filter((claim) => claim.evidenceId === source.evidenceId)
      .map((claim) => claim.claimId),
    verification: "verified",
    availability: "observed"
  })),
  review: {
    status: "approved",
    decisionId: "decision_demo_support_refund_approved",
    stateVersion: 17,
    idempotency: "accepted replay-safe decision"
  },
  verification: {
    snapshot: "verification_snapshot_support_refund_v1",
    baselineOrigin: "declared_fixture",
    status: "verified",
    publicationFreshness: "current"
  },
  artifact: {
    id: researchBriefFixture.report.artifactId,
    mediaType: researchBriefFixture.report.mediaType,
    revision: "publication_rev_1",
    contentHash: researchBriefFixture.report.contentHash,
    safety: "hash verified / unsafe content rejected"
  },
  resultMarkdown: researchBriefFixture.report.content,
  failureCause: {
    kind: "not_applicable"
  } as const,
  cliGoldenPath: [
    "python tools/decision_research_agent_tool.py run \\",
    '  --query "Compare the evidence behind the proposed decision" \\',
    "  --wait \\",
    "  --result"
  ].join("\n")
};

export const blockedDemoRun = {
  service: "decision-research-agent",
  mode: "demo data",
  health: "unavailable",
  runId: "run_demo_support_refund_blocked",
  threadId: "demo-thread-support-refund-blocked",
  segmentId: "run_demo_support_refund_blocked_seg_review",
  stateVersion: 6,
  profileId: "generic-research",
  lifecycle: [
    "created",
    "planning",
    "tool_call",
    "tool_failed",
    "evidence_incomplete",
    "review_required"
  ],
  telemetry: [
    "session_created",
    "plan_recorded",
    "tool_start: declared_fixture_read",
    "tool_failure: policy_access_unconfirmed",
    "review_required"
  ],
  evidence: [
    {
      ...demoRun.evidence[0],
      citedBy: ["claim_bounded_assistant"]
    },
    {
      ...demoRun.evidence[1],
      citedBy: [],
      verification: "access_unconfirmed",
      availability: "unconfirmed"
    },
    {
      ...demoRun.evidence[2],
      citedBy: [],
      verification: "access_unconfirmed",
      availability: "unconfirmed"
    }
  ],
  review: {
    status: "review_required",
    decisionId: "decision_pending_support_refund_review",
    stateVersion: 6,
    idempotency: "not created"
  },
  verification: {
    snapshot: "verification_pending_support_refund",
    baselineOrigin: "synthetic_demo",
    status: "blocked",
    publicationFreshness: "not published"
  },
  artifact: {
    id: researchBriefFixture.report.artifactId,
    mediaType: researchBriefFixture.report.mediaType,
    revision: "not published",
    contentHash: "sha256:not-delivered",
    safety: "not evaluated"
  },
  resultMarkdown: "",
  failureCause: {
    kind: "observed",
    schema_version: "dra.run-failure-cause.v1",
    phase: "execution",
    code: "execution_error",
    recorded_at: "2026-09-16T00:00:00Z"
  } as const,
  cliGoldenPath: demoRun.cliGoldenPath
};

export async function validateResearchBriefFixture(
  fixture: ResearchBriefFixture = researchBriefFixture
): Promise<readonly string[]> {
  const errors: string[] = [];
  const sourceById = new Map(fixture.sources.map((source) => [source.evidenceId, source]));
  const claimIds = new Set<string>();

  if (fixture.question.trim().length === 0) {
    errors.push("question is empty");
  }
  if (fixture.sources.length !== 3) {
    errors.push("expected exactly three source fixtures");
  }

  if (sourceById.size !== fixture.sources.length) {
    errors.push("duplicate evidence id");
  }

  for (const claim of fixture.claims) {
    if (claimIds.has(claim.claimId)) {
      errors.push(`duplicate claim id: ${claim.claimId}`);
    }
    claimIds.add(claim.claimId);
    const source = sourceById.get(claim.evidenceId);
    if (!source) {
      errors.push(`missing evidence id: ${claim.evidenceId}`);
      continue;
    }
    if (!source.content.includes(claim.excerpt)) {
      errors.push(`excerpt mismatch: ${claim.claimId}`);
    }
  }

  const expectedHashes = await Promise.all([
    ...fixture.sources.map(async (source) => [source.evidenceId, await sha256Text(source.content)] as const),
    ["report", await sha256Text(fixture.report.content)] as const
  ]);
  const hashById = new Map(expectedHashes);

  for (const source of fixture.sources) {
    if (source.fingerprint !== `sha256:${hashById.get(source.evidenceId)}`) {
      errors.push(`source hash mismatch: ${source.evidenceId}`);
    }
  }
  if (fixture.report.contentHash !== `sha256:${hashById.get("report")}`) {
    errors.push("report hash mismatch");
  }

  return Object.freeze(errors);
}

async function sha256Text(value: string): Promise<string> {
  const digest = await globalThis.crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(value)
  );
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export const architectureNodes = [
  "OpenClaw / Codex / Tool Client / REST",
  "FastAPI",
  "ResearchExecutionService",
  "DeepAgentsHarness",
  "LangChain Agent Framework",
  "LangGraph Runtime",
  "Application DB Authority",
  "LangSmith Diagnostics"
];
