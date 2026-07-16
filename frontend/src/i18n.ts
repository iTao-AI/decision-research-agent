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
      staticDescription: "使用内置静态快照，适合无后端面试演示。",
      liveDescription: "连接本机后端，执行受控 run -> result 黄金路径。",
      baseUrl: "Backend base URL",
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
