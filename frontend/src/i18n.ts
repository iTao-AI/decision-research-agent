export type Language = "zh" | "en";

export const screenKeys = [
  "command",
  "lifecycle",
  "evidence",
  "review",
  "result",
  "architecture"
] as const;

export type ScreenKey = (typeof screenKeys)[number];

export const screenEnglishNames: Record<ScreenKey, string> = {
  command: "Command Center",
  lifecycle: "Run Lifecycle",
  evidence: "Evidence Ledger",
  review: "Review / Verification",
  result: "Canonical Result",
  architecture: "Architecture Explain Mode"
};

export const copy = {
  zh: {
    navLabel: "Demo console screens",
    eyebrow: "Agent-first / human-governed / Evidence-governed",
    language: "语言",
    chinese: "中文",
    english: "English",
    subtitle:
      "研究运行演示控制台：可触发 ResearchRun、观察生命周期并获取 canonical result，但不拥有业务 authority。",
    boundaryStatement:
      "Static Demo 和有界 Live Backend consumer 仅用于演示研究运行链路。Demo console 不新增 backend state、DB table、API path、login、RBAC、tenant model、public online runner 或 PDF export。",
    screens: {
      command: "研究运行演示控制台",
      lifecycle: "运行生命周期",
      evidence: "证据账本",
      review: "人工复核 / 核验",
      result: "标准交付物",
      architecture: "架构解释模式"
    },
    labels: {
      health: "Health",
      mode: "Mode",
      service: "Service",
      run: "Run",
      lifecycle: "Lifecycle",
      telemetry: "Timeline",
      evidence: "Evidence refs",
      citedBy: "Claim refs",
      verification: "Verification",
      review: "Review",
      artifact: "Artifact",
      boundaries: "边界",
      cli: "CLI 黄金路径",
      authority: "Authority",
      live: "Live Demo"
    },
    observations: {
      notObserved: "尚未观察到",
      notApplicable: "不适用",
      unsupported: "当前后端不支持",
      observedEmptyEvidence: "已观察：Evidence 为空",
      observedEmptyCollection: "已观察：列表为空",
      terminalNoResult: "已观察终态，但 canonical result 尚未就绪",
      referenceOnly: "参考说明：不表示当前 run 已启用全部可选 runtime。"
    },
    projection: {
      staticSnapshot: "静态演示快照",
      liveProjection: "Live service projection",
      createReceipt: "Create acknowledgement",
      runState: "Run state",
      publication: "Publication metadata",
      artifacts: "Artifact metadata",
      failureCause: "Failure cause",
      stateProjection: "当前持久化状态投影",
      eventHistory: "静态生命周期示意",
      workflow: "Review workflow",
      decision: "Review decision",
      resolution: "Review resolution"
    },
    live: {
      staticMode: "静态演示",
      liveMode: "真实后端",
      staticDescription: "使用内置静态快照，适合无后端演示。",
      liveDescription: "连接本机后端，执行受控 run -> result 黄金路径。",
      baseUrl: "Backend base URL",
      question: "研究问题",
      questionHint: "初始示例可编辑；本页仅暂存输入，运行后由后端拥有状态与结果。",
      queryBytes: (current: number) => `UTF-8 bytes: ${current} / 4096`,
      queryBlank: "请先输入研究问题。",
      queryTooLarge: "请将研究问题缩短到 4096 UTF-8 bytes 以内。",
      checkHealth: "检查后端",
      runResult: "运行并获取结果",
      backendAvailable: "后端可用",
      noResult: "尚未获取 live result。",
      status: "Live 状态",
      fix: "修复建议",
      resultPreview: "Canonical Result Preview",
      startBackend: "启动后端或检查 Backend base URL。",
      retrySameRequest: "重试同一请求",
      discardPendingRequest: "丢弃待确认请求",
      resumeObservation: "仅 GET 恢复观察",
      originalReceipt: "新建请求确认",
      replayReceipt: "幂等重放确认",
      statuses: {
        checking: "正在检查后端健康状态",
        creating: "正在创建 ResearchRun",
        error: "需要操作方处理",
        idle: "等待检查后端",
        observation_interrupted: "观察已中断，可按 run_id 继续",
        polling: "正在轮询运行状态",
        ready: "后端已就绪",
        reconciliation_required: "创建响应不明确，需要确认",
        result: "已加载 canonical result",
        static: "静态快照已启用",
        terminal: "已观察到非 ready 终态"
      }
    },
    showcase: {
      railLabel: "研究路径",
      workspaceLabel: "研究工作区",
      questionLabel: "研究问题",
      question: "比较两种研究工作流的证据完整性与交付边界",
      normalBadge: "正常路径 · 已交付",
      blockedBadge: "需要复核",
      judgmentLabel: "判断侧栏",
      technicalLabel: "Technical console view",
      technicalDescription: "运行模式、内部标识、框架细节与诊断信息",
      stageStatus: {
        current: "当前",
        nextCheckpoint: "下一检查点"
      },
      stages: {
        question: "问题",
        work: "计划与工具工作",
        evidence: "Evidence review",
        review: "判断与交付",
        delivery: "Canonical delivery"
      },
      overview: {
        summary: "计划、工具工作和 Evidence 已收敛为可交付的研究结果。",
        planTitle: "Plan",
        plan: "定义比较维度，先固定可审查的来源范围。",
        toolTitle: "Tool work",
        tool: "读取声明来源并记录每一步的 Evidence ref。",
        evidenceTitle: "Evidence",
        evidence: "2 条 Evidence 已冻结，claim 与 source 可回溯。",
        reviewTitle: "Judgment",
        review: "Review approved；verification 保持独立。",
        deliveryTitle: "Canonical delivery",
        delivery: "canonical result 已由 service-owned contract 交付。",
        statuses: {
          captured: "已捕获",
          recorded: "已记录",
          frozen: "已冻结",
          approved: "已批准",
          ready: "已就绪"
        }
      },
      evidence: {
        summary: "已交付结果保留 claim、source 和 verification 的交付前复核记录。",
        heading: "Claim / source 复核",
        traceable: "已交付结果保留交付前复核记录",
        reviewPhase: "交付前复核记录",
        claim: "Claim",
        source: "Source",
        citation: "Citation",
        verified: "verified",
        cited: "cited",
        pending: "需要独立核验",
        notObserved: "尚未观察到",
        delivery: "Canonical delivery",
        delivered: "canonical result 已交付"
      },
      blocked: {
        summary: "缺少足够 Evidence、citation 无效或 tool failure 时，交付保持关闭。",
        heading: "失败运行检查点",
        warning: "Evidence 不足或 citation 无效",
        detail: "请检查已持久化的 failure cause 与处置。原失败运行保持 immutable 且不交付；UI 不会 resume、自动 retry 或自动创建 replacement。",
        diagnostic: "诊断链",
        firstFailingStep: "首个显示失败步骤",
        firstFailingStepDetail: "这是生命周期中首先显示为失败的步骤，不等同于已证明的根因。",
        terminalCause: "持久化终态原因",
        terminalCauseDetail: "现有 dra.run-failure-cause.v1 observation",
        disposition: "既有处置",
        dispositionDetail: "service-owned review / delivery 状态",
        review: "review_required",
        delivery: "not_delivered",
        deliveryTitle: "原失败运行保持 immutable",
        deliveryDetail: "Evidence 与 citation 问题仍需人工复核。新的执行只能由调用方发起：普通 new run，或在符合条件时显式 one-hop replacement。",
        recovery: "后续执行边界",
        trackEvidence: "Evidence / citation",
        trackReview: "人工复核",
        trackResult: "不交付",
        evidenceSignal: "Evidence 信号"
      },
      judgment: {
        gateChecks: "门控检查",
        badgeReady: "已就绪",
        badgeBlocked: "已阻断",
        badgeObserved: "已观察",
        badgeNotObserved: "尚未观察到",
        evidenceTraceable: "可追溯",
        evidenceInsufficient: "不足",
        decisionObserved: "decision 已观察",
        evidenceGateTitle: "Evidence 门控",
        liveSummary: "当前仅显示 service-owned observation；未观察到的事实不会被推断。"
      },
      live: {
        badge: "Live service projection",
        title: "Live 服务状态",
        summary: "仅显示当前 service-owned observation；未观察到的 Evidence、Review 或 delivery 不会被推断。",
        evidenceObserved: "条 Evidence 已观察",
        resultObserved: "canonical result 已观察",
        resultNotObserved: "canonical result 尚未观察到"
      }
    },
    statements: {
      command:
        "DRA 是 research capability service，不是聊天机器人。UI 可触发 ResearchRun 并消费 service-owned state，但不创建业务事实源。",
      lifecycle:
        "同一个 run_id 贯穿 telemetry、token usage、WebSocket、artifact 和 result。终态写入由 fenced finalization 控制。",
      evidence:
        "Evidence 是 run-scoped append-only snapshot。cited 不等于 verified，人工 verification 是独立 decision。",
      review:
        "Review approval 允许交付，但不验证 Evidence；verification snapshot 和 publication revision 保持 append-only。",
      result:
        "UI 不定义最终答案；canonical result 仍由 GET /api/runs/{run_id}/result contract 选择。",
      architecture:
        "Framework owns execution context. Service owns business facts. UI starts runs and consumes public contracts without owning authority."
    }
  },
  en: {
    navLabel: "Demo console screens",
    eyebrow: "Agent-first / human-governed / Evidence-governed",
    language: "Language",
    chinese: "中文",
    english: "English",
    subtitle:
      "Agent Research Operations Console: starts ResearchRuns, observes lifecycle, and retrieves canonical results without owning business authority.",
    boundaryStatement:
      "Static fallback plus bounded Live Backend consumer. No backend state, DB table, API path, login, RBAC, tenant model, public online runner, or PDF export is added by the demo console.",
    screens: {
      command: "Agent Research Operations Console",
      lifecycle: "Run Lifecycle",
      evidence: "Evidence Ledger",
      review: "Human Review / Verification",
      result: "Canonical Result",
      architecture: "Runtime Boundaries"
    },
    labels: {
      health: "Health",
      mode: "Mode",
      service: "Service",
      run: "Run",
      lifecycle: "Lifecycle",
      telemetry: "Timeline",
      evidence: "Evidence refs",
      citedBy: "Claim refs",
      verification: "Verification",
      review: "Review",
      artifact: "Artifact",
      boundaries: "Boundaries",
      cli: "CLI golden path",
      authority: "Authority",
      live: "Live Demo"
    },
    observations: {
      notObserved: "Not observed",
      notApplicable: "Not applicable",
      unsupported: "Unsupported by the current backend",
      observedEmptyEvidence: "Observed: Evidence ledger is empty",
      observedEmptyCollection: "Observed: collection is empty",
      terminalNoResult: "Terminal state observed; canonical result is not ready",
      referenceOnly: "Reference only: this does not claim every optional runtime is active."
    },
    projection: {
      staticSnapshot: "Static demo snapshot",
      liveProjection: "Live service projection",
      createReceipt: "Create acknowledgement",
      runState: "Run state",
      publication: "Publication metadata",
      artifacts: "Artifact metadata",
      failureCause: "Failure cause",
      stateProjection: "Current persisted state projection",
      eventHistory: "Static lifecycle illustration",
      workflow: "Review workflow",
      decision: "Review decision",
      resolution: "Review resolution"
    },
    live: {
      staticMode: "Static Demo",
      liveMode: "Live Backend",
      staticDescription: "Use the bundled static snapshot when the backend is unavailable.",
      liveDescription: "Connect to a local backend and run the bounded run -> result golden path.",
      baseUrl: "Backend base URL",
      question: "Research question",
      questionHint:
        "The initial example is editable; this page only holds the input temporarily. The backend owns status and results after the run starts.",
      queryBytes: (current: number) => `UTF-8 bytes: ${current} / 4096`,
      queryBlank: "Enter a research question before starting a run.",
      queryTooLarge: "Shorten the research question to 4096 UTF-8 bytes or fewer.",
      checkHealth: "Check backend",
      runResult: "Run and fetch result",
      backendAvailable: "Backend available",
      noResult: "No live result has been fetched yet.",
      status: "Live status",
      fix: "Fix",
      resultPreview: "Canonical Result Preview",
      startBackend: "Start the backend or verify Backend base URL.",
      retrySameRequest: "Retry same request",
      discardPendingRequest: "Discard pending request",
      resumeObservation: "Resume observation (GET only)",
      originalReceipt: "New create acknowledgement",
      replayReceipt: "Idempotent replay acknowledgement",
      statuses: {
        checking: "Checking backend health",
        creating: "Starting ResearchRun",
        error: "Operator action required",
        idle: "Ready for backend check",
        observation_interrupted: "Observation interrupted; resume by run_id",
        polling: "Polling run state",
        ready: "Backend ready",
        reconciliation_required: "Create response is ambiguous and needs reconciliation",
        result: "Canonical result loaded",
        static: "Static snapshot active",
        terminal: "Terminal non-ready run observed"
      }
    },
    showcase: {
      railLabel: "Research flow",
      workspaceLabel: "Research workspace",
      questionLabel: "Research question",
      question: "Compare evidence completeness and delivery boundaries across two research workflows",
      normalBadge: "Normal path · delivered",
      blockedBadge: "Review required",
      judgmentLabel: "Judgment sidebar",
      technicalLabel: "Technical console view",
      technicalDescription: "Runtime mode, internal identifiers, framework details, and diagnostics",
      stageStatus: {
        current: "current",
        nextCheckpoint: "next checkpoint"
      },
      stages: {
        question: "Question",
        work: "Plan + tool work",
        evidence: "Evidence review",
        review: "Judgment + review",
        delivery: "Canonical delivery"
      },
      overview: {
        summary: "Plan, tool work, and Evidence converge into a deliverable research result.",
        planTitle: "Plan",
        plan: "Fix comparison dimensions and the auditable source boundary first.",
        toolTitle: "Tool work",
        tool: "Read declared sources and record an Evidence ref for each step.",
        evidenceTitle: "Evidence",
        evidence: "Two Evidence entries are frozen and traceable to claims.",
        reviewTitle: "Judgment",
        review: "Review approved; verification remains an independent decision.",
        deliveryTitle: "Canonical delivery",
        delivery: "The service-owned contract supplies the canonical result.",
        statuses: {
          captured: "captured",
          recorded: "recorded",
          frozen: "frozen",
          approved: "approved",
          ready: "ready"
        }
      },
      evidence: {
        summary: "The delivered result retains its pre-delivery claim, source, and verification review record.",
        heading: "Claim / source review",
        traceable: "Delivered result retains its pre-delivery review record",
        reviewPhase: "pre-delivery review retained",
        claim: "Claim",
        source: "Source",
        citation: "Citation",
        verified: "verified",
        cited: "cited",
        pending: "Independent verification required",
        notObserved: "Not observed",
        delivery: "Canonical delivery",
        delivered: "Canonical result delivered"
      },
      blocked: {
        summary: "When Evidence is insufficient, a citation is invalid, or a tool fails, delivery stays closed.",
        heading: "Failed-run checkpoint",
        warning: "Evidence is insufficient or the citation is invalid",
        detail: "Inspect the persisted failure cause and disposition. The failed source remains immutable and not delivered; the UI cannot resume it, retry automatically, or create a replacement automatically.",
        diagnostic: "Diagnostic chain",
        firstFailingStep: "First displayed failing step",
        firstFailingStepDetail: "The first displayed failing step is not a proven root cause.",
        terminalCause: "Durable terminal cause",
        terminalCauseDetail: "Existing dra.run-failure-cause.v1 observation",
        disposition: "Disposition",
        dispositionDetail: "Service-owned review / delivery state",
        review: "review_required",
        delivery: "not_delivered",
        deliveryTitle: "Failed source remains immutable",
        deliveryDetail: "Evidence and citation issues still require human review. Any new execution is caller-initiated as an ordinary new run or, when eligible, an explicit one-hop replacement.",
        recovery: "Next execution boundary",
        trackEvidence: "Evidence / citation",
        trackReview: "Human review",
        trackResult: "Not delivered",
        evidenceSignal: "Evidence signal"
      },
      judgment: {
        gateChecks: "GATE CHECKS",
        badgeReady: "ready",
        badgeBlocked: "blocked",
        badgeObserved: "observed",
        badgeNotObserved: "not observed",
        evidenceTraceable: "traceable",
        evidenceInsufficient: "insufficient",
        decisionObserved: "decision observed",
        evidenceGateTitle: "Evidence gate",
        liveSummary: "Only service-owned observations are shown; unobserved facts are not inferred."
      },
      live: {
        badge: "Live service projection",
        title: "Live service state",
        summary: "Only the current service-owned observation is shown; unobserved Evidence, Review, or delivery is not inferred.",
        evidenceObserved: "Evidence entries observed",
        resultObserved: "Canonical result observed",
        resultNotObserved: "Canonical result not observed"
      }
    },
    statements: {
      command:
        "DRA is a research capability service, not a chatbot. The UI starts ResearchRuns and consumes service-owned state without becoming a business authority.",
      lifecycle:
        "The same run_id scopes telemetry, token usage, WebSocket events, artifacts, and result delivery. Terminal writes are fenced.",
      evidence:
        "Evidence is a run-scoped append-only snapshot. Cited does not mean verified; human verification is a separate decision.",
      review:
        "Review approval permits delivery but does not verify Evidence; verification snapshots and publication revisions remain append-only.",
      result:
        "The UI does not define the answer; the canonical result is selected by GET /api/runs/{run_id}/result.",
      architecture:
        "Framework owns execution context. Service owns business facts. UI starts runs and consumes public contracts without owning authority."
    }
  }
} as const;
