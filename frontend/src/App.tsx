import { type ReactNode, useEffect, useMemo, useState } from "react";

import {
  DEFAULT_LIVE_DEMO_QUERY,
  type ClientError,
  validateLiveDemoQuery
} from "./apiClient";
import {
  buildLiveConsoleProjection,
  buildStaticConsoleProjection,
  type ConsoleProjection,
  type FailureCauseView,
  type Observation,
  type StaticShowcaseScenario
} from "./consoleProjection";
import { copy, type Language, screenEnglishNames, screenKeys, type ScreenKey } from "./i18n";
import { type LiveRunOptions, useLiveRun } from "./useLiveRun";

const authorityBadges = [
  "Application DB",
  "LangGraph checkpoint",
  "LangSmith diagnostics",
  "GET /api/runs/{run_id}/result"
];

export type ShowcaseState = "overview" | "evidence" | "blocked";

type StageKey = "question" | "work" | "evidence" | "review" | "delivery";

const stageKeys: StageKey[] = ["question", "work", "evidence", "review", "delivery"];

const stageScreens: Record<StageKey, ScreenKey> = {
  question: "command",
  work: "lifecycle",
  evidence: "evidence",
  review: "review",
  delivery: "result"
};

export default function App({
  liveOptions,
  showcaseState: providedShowcaseState
}: {
  liveOptions?: LiveRunOptions;
  showcaseState?: ShowcaseState;
}) {
  const route = providedShowcaseState
    ? { state: providedShowcaseState, isShowcaseRoute: true }
    : readShowcaseRoute();
  const showcaseState = route.state;
  const staticScenario: StaticShowcaseScenario = showcaseState === "blocked" ? "blocked" : "normal";
  const isShowcaseRoute = route.isShowcaseRoute;
  const [language, setLanguage] = useState<Language>("zh");
  const [activeScreen, setActiveScreen] = useState<ScreenKey>(() =>
    isShowcaseRoute ? stageScreens[initialStage(showcaseState)] : "command"
  );
  const liveRun = useLiveRun(liveOptions);
  const t = copy[language];
  const projection = useMemo(
    () =>
      liveRun.state.mode === "static"
        ? staticScenario === "normal"
          ? buildStaticConsoleProjection()
          : buildStaticConsoleProjection(staticScenario)
        : buildLiveConsoleProjection({
            health: liveRun.state.health,
            created: liveRun.state.created,
            run: liveRun.state.run,
            result: liveRun.state.result,
            status: liveRun.state.status
          }),
    [liveRun.state, staticScenario]
  );
  const isStaticProjection = projection.source === "static";

  const activeTitle = t.screens[activeScreen];
  const activeStatement = t.statements[activeScreen];
  const screenSummary = useMemo(() => buildScreenSummary(activeScreen), [activeScreen]);

  useEffect(() => {
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  }, [language]);

  return (
    <div className={`console-shell showcase-${showcaseState} ${isShowcaseRoute ? "showcase-route" : ""}`}>
      <header className="top-bar">
        <div>
          <p className="eyebrow">{t.eyebrow}</p>
          <h1>{isShowcaseRoute ? t.showcase.workspaceLabel : activeTitle}</h1>
          <p className="subtitle">{t.subtitle}</p>
        </div>
        <div className="top-actions" aria-label={t.language}>
          <span>{t.language}</span>
          <button
            className={language === "zh" ? "active" : ""}
            type="button"
            onClick={() => setLanguage("zh")}
          >
            {t.chinese}
          </button>
          <button
            className={language === "en" ? "active" : ""}
            type="button"
            onClick={() => setLanguage("en")}
          >
            {t.english}
          </button>
        </div>
      </header>

      <div className="workspace">
        <StageRail
          activeScreen={activeScreen}
          isShowcaseRoute={isShowcaseRoute}
          language={language}
          onSelectScreen={setActiveScreen}
        />

        <main className={`canvas ${liveRun.state.mode}-mode`}>
          {isStaticProjection ? (
            <section className="research-work-surface">
              <div className="surface-heading">
                <div>
                  <p className="kicker">{t.showcase.workspaceLabel}</p>
                  <p className="surface-label">{t.showcase.questionLabel}</p>
                  <h2>{t.showcase.question}</h2>
                </div>
                <span className={`showcase-badge ${showcaseState === "blocked" ? "blocked" : "ready"}`}>
                  {showcaseState === "blocked" ? t.showcase.blockedBadge : t.showcase.normalBadge}
                </span>
              </div>
              <p className="surface-summary">
                {showcaseState === "blocked"
                  ? t.showcase.blocked.summary
                  : showcaseState === "evidence"
                    ? t.showcase.evidence.summary
                    : t.showcase.overview.summary}
              </p>
              <ShowcaseWorkspace
                language={language}
                projection={projection}
                showcaseState={showcaseState}
              />
            </section>
          ) : (
            <LiveObservationSurface language={language} projection={projection} />
          )}

          <details
            className="technical-disclosure technical-console-view"
            open={!isShowcaseRoute || !isStaticProjection}
          >
            <summary>
              <span>{t.showcase.technicalLabel}</span>
              <small>{t.showcase.technicalDescription}</small>
            </summary>
            <section className="status-grid" aria-label="Run state summary">
              <Metric
                label={t.labels.service}
                value={observationLabel(projection.summary.service, language)}
                tone="blue"
              />
              <Metric
                label={t.labels.health}
                value={observationLabel(projection.summary.health, language)}
                tone="amber"
              />
              <Metric label={t.labels.mode} value={projection.summary.mode} tone="cyan" />
              <Metric
                label={t.labels.run}
                value={observationLabel(projection.summary.runId, language)}
                tone="green"
              />
            </section>
            <section className="primary-panel">
              <div className="panel-heading">
                <div>
                  <p className="kicker">{screenEnglishNames[activeScreen]}</p>
                  <h2>{screenEnglishNames[activeScreen]}</h2>
                </div>
                <span className="status-pill">{screenSummary}</span>
              </div>
              <p className="statement">{activeStatement}</p>

              {activeScreen === "command" && (
                <CommandCenter language={language} projection={projection} />
              )}
              {activeScreen === "lifecycle" && (
                <RunLifecycle language={language} projection={projection} />
              )}
              {activeScreen === "evidence" && (
                <EvidenceLedger language={language} projection={projection} />
              )}
              {activeScreen === "review" && (
                <ReviewVerification language={language} projection={projection} />
              )}
              {activeScreen === "result" && (
                <CanonicalResult language={language} projection={projection} />
              )}
              {activeScreen === "architecture" && (
                <ArchitectureMode language={language} projection={projection} />
              )}
            </section>
          </details>

          <details
            className="technical-disclosure technical-live-view"
            open={!isShowcaseRoute || !isStaticProjection}
          >
            <summary>
              <span>{t.live.status}</span>
              <small>{t.live.liveDescription}</small>
            </summary>
            <LiveDemoPanel language={language} liveRun={liveRun} projection={projection} />
          </details>
        </main>

        {isStaticProjection ? (
          <JudgmentSidebar
            isShowcaseRoute={isShowcaseRoute}
            language={language}
            projection={projection}
            showcaseState={showcaseState}
          />
        ) : (
          <LiveJudgmentSidebar language={language} projection={projection} />
        )}
      </div>
    </div>
  );
}

function readShowcaseRoute(): { state: ShowcaseState; isShowcaseRoute: boolean } {
  if (typeof window === "undefined") {
    return { state: "overview", isShowcaseRoute: false };
  }
  const value = new URLSearchParams(window.location.search).get("showcase");
  if (value === "evidence" || value === "blocked" || value === "overview") {
    return { state: value, isShowcaseRoute: true };
  }
  return { state: "overview", isShowcaseRoute: false };
}

function initialStage(showcaseState: ShowcaseState): StageKey {
  return showcaseState === "evidence" ? "evidence" : showcaseState === "blocked" ? "review" : "work";
}

function StageRail({
  activeScreen,
  isShowcaseRoute,
  language,
  onSelectScreen
}: {
  activeScreen: ScreenKey;
  isShowcaseRoute: boolean;
  language: Language;
  onSelectScreen: (screen: ScreenKey) => void;
}) {
  const t = copy[language];
  const selectedStage = stageKeys.find((stage) => stageScreens[stage] === activeScreen) ?? "work";

  return (
    <aside className="stage-rail left-rail">
      <div className="rail-heading">
        <span className="rail-marker">01</span>
        <div>
          <p className="rail-kicker">DRA / DELIVERY PATH</p>
          <h2>{t.showcase.railLabel}</h2>
        </div>
      </div>
      <nav aria-label="Research flow" className="stage-navigation">
        {stageKeys.map((stage, index) => (
          <button
            className={stage === selectedStage ? "stage-item active" : "stage-item"}
            key={stage}
            type="button"
            onClick={() => onSelectScreen(stageScreens[stage])}
          >
            <span className="stage-number">{String(index + 1).padStart(2, "0")}</span>
            <span>
              <strong>{t.showcase.stages[stage]}</strong>
              <small>
                {stage === selectedStage
                  ? t.showcase.stageStatus.current
                  : t.showcase.stageStatus.nextCheckpoint}
              </small>
            </span>
          </button>
        ))}
      </nav>
      <div className="rail-footer">
        <span className="rail-footer-dot" aria-hidden="true" />
        <p>{t.showcase.technicalDescription}</p>
      </div>

      {!isShowcaseRoute && (
        <details className="technical-disclosure technical-navigation" open>
          <summary>
            <span>{t.navLabel}</span>
            <small>{t.showcase.technicalDescription}</small>
          </summary>
          <nav aria-label={t.navLabel}>
            {screenKeys.map((screenKey) => (
              <button
                aria-label={screenEnglishNames[screenKey]}
                className={screenKey === activeScreen ? "nav-item active" : "nav-item"}
                key={screenKey}
                type="button"
                onClick={() => onSelectScreen(screenKey)}
              >
                <span>{t.screens[screenKey]}</span>
                <small>{screenEnglishNames[screenKey]}</small>
              </button>
            ))}
          </nav>
        </details>
      )}
    </aside>
  );
}

function ShowcaseWorkspace({
  language,
  projection,
  showcaseState
}: {
  language: Language;
  projection: ConsoleProjection;
  showcaseState: ShowcaseState;
}) {
  if (showcaseState === "blocked") {
    return <BlockedShowcase language={language} projection={projection} />;
  }
  if (showcaseState === "evidence") {
    return <EvidenceShowcase language={language} projection={projection} />;
  }
  return <OverviewShowcase language={language} />;
}

function LiveObservationSurface({
  language,
  projection
}: {
  language: Language;
  projection: ConsoleProjection;
}) {
  const t = copy[language];
  const deliveryObservation: Observation<string> =
    projection.command.run.kind === "observed"
      ? projection.command.run.value.deliveryStatus
      : { kind: "not_observed" };
  const evidenceSummary =
    projection.evidence.kind === "observed"
      ? `${projection.evidence.value.length} ${t.showcase.live.evidenceObserved}`
      : observationLabel(projection.evidence, language);
  const resultSummary =
    projection.result.kind === "observed"
      ? t.showcase.live.resultObserved
      : t.showcase.live.resultNotObserved;

  return (
    <section className="research-work-surface live-observation-surface">
      <div className="surface-heading">
        <div>
          <p className="kicker">{t.showcase.live.title}</p>
          <p className="surface-label">{t.labels.mode}</p>
          <h2>{t.showcase.live.summary}</h2>
        </div>
        <span className="showcase-badge neutral">{t.showcase.live.badge}</span>
      </div>
      <div className="live-observation-grid">
        <article>
          <span>{t.labels.health}</span>
          <ObservationValue language={language} observation={projection.summary.health} />
        </article>
        <article>
          <span>{t.labels.run}</span>
          <ObservationValue language={language} observation={projection.summary.runId} />
        </article>
        <article>
          <span>{t.labels.evidence}</span>
          <strong>{evidenceSummary}</strong>
        </article>
        <article>
          <span>{t.labels.review}</span>
          <ObservationValue language={language} observation={projection.review.status} />
        </article>
        <article>
          <span>{t.showcase.stages.delivery}</span>
          <ObservationValue language={language} observation={deliveryObservation} />
        </article>
        <article>
          <span>{t.labels.artifact}</span>
          <strong>{resultSummary}</strong>
        </article>
      </div>
    </section>
  );
}

function OverviewShowcase({ language }: { language: Language }) {
  const t = copy[language].showcase.overview;
  const steps = [
    ["01", copy[language].showcase.stages.question, t.planTitle, t.plan, t.statuses.captured],
    ["02", copy[language].showcase.stages.work, t.toolTitle, t.tool, t.statuses.recorded],
    ["03", copy[language].showcase.stages.evidence, t.evidenceTitle, t.evidence, t.statuses.frozen],
    ["04", copy[language].showcase.stages.review, t.reviewTitle, t.review, t.statuses.approved],
    ["05", copy[language].showcase.stages.delivery, t.deliveryTitle, t.delivery, t.statuses.ready]
  ] as const;

  return (
    <div className="showcase-overview">
      <div className="showcase-flow-line" aria-hidden="true">
        <span />
        <span />
        <span />
        <span />
      </div>
      <div className="showcase-step-grid">
        {steps.map(([number, stage, title, detail, status]) => (
          <article className="showcase-step" key={number}>
            <div className="step-heading">
              <span className="step-number">{number}</span>
              <span className="step-status">{status}</span>
            </div>
            <p className="step-stage">{stage}</p>
            <h3>{title}</h3>
            <p>{detail}</p>
          </article>
        ))}
      </div>
    </div>
  );
}

function EvidenceShowcase({
  language,
  projection
}: {
  language: Language;
  projection: ConsoleProjection;
}) {
  const t = copy[language].showcase.evidence;
  const evidence = projection.evidence.kind === "observed" ? projection.evidence.value : [];

  return (
    <div className="evidence-showcase">
      <div className="review-banner">
        <span className="review-banner-mark">02</span>
        <div>
          <p className="step-stage">{t.heading}</p>
          <h3>{t.traceable}</h3>
        </div>
        <span className="step-status">{t.reviewPhase}</span>
      </div>
      <div className="evidence-review-grid">
        {evidence.map((entry) => (
          <article className="evidence-review-card" key={entry.evidenceId}>
            <div className="evidence-review-card-heading">
              <strong>{entry.evidenceId}</strong>
              <span>{entry.verificationStatus}</span>
            </div>
            <div className="review-field">
              <span>{t.claim}</span>
              <strong>
                {entry.citedBy.kind === "observed"
                  ? entry.citedBy.value.join(" · ")
                  : t.notObserved}
              </strong>
            </div>
            <div className="review-field">
              <span>{t.source}</span>
              <strong>{entry.sourceIdentity}</strong>
            </div>
            <div className="review-field">
              <span>citation_status</span>
              <strong>{
                entry.citationStatus.kind === "observed"
                  ? entry.citationStatus.value
                  : t.pending
              }</strong>
            </div>
            <code>{entry.fingerprint}</code>
          </article>
        ))}
      </div>
      <div className="evidence-review-footer">
        <span>{t.delivery}</span>
        <strong>{t.delivered}</strong>
      </div>
    </div>
  );
}

function BlockedShowcase({
  language,
  projection
}: {
  language: Language;
  projection: ConsoleProjection;
}) {
  const t = copy[language].showcase.blocked;
  const firstFailingStep =
    projection.lifecycle.entries.kind === "observed"
      ? projection.lifecycle.entries.value.find(
          (entry) =>
            entry.category === "lifecycle" &&
            entry.status.kind === "observed" &&
            entry.status.value === "tool_failed"
        )
      : undefined;
  const firstFailingStepValue = firstFailingStep?.label ?? copy[language].observations.notObserved;
  const terminalCauseValue = diagnosticFailureCause(projection.lifecycle.failureCause, language);
  const dispositionValue = diagnosticDisposition(projection, language);

  return (
    <div className="blocked-showcase">
      <article className="blocked-callout">
        <div className="blocked-callout-heading">
          <span className="blocked-icon" aria-hidden="true">!</span>
          <div>
            <p className="step-stage">{t.heading}</p>
            <h3>{t.warning}</h3>
          </div>
        </div>
        <p>{t.detail}</p>
        <div className="blocked-status-row">
          <span>review_status</span>
          <strong>{t.review}</strong>
        </div>
        <div className="blocked-status-row">
          <span>delivery_status</span>
          <strong>{t.delivery}</strong>
        </div>
        <div className="blocked-diagnostic-card">
          <p className="step-stage">{t.diagnostic}</p>
          <div className="blocked-diagnostic-grid">
            <div className="blocked-diagnostic-node">
              <span>{t.firstFailingStep}</span>
              <strong>{firstFailingStepValue}</strong>
              <small>{t.firstFailingStepDetail}</small>
            </div>
            <div className="blocked-diagnostic-node">
              <span>{t.terminalCause}</span>
              <strong>{terminalCauseValue}</strong>
              <small>{t.terminalCauseDetail}</small>
            </div>
            <div className="blocked-diagnostic-node">
              <span>{t.disposition}</span>
              <strong>{dispositionValue}</strong>
              <small>{t.dispositionDetail}</small>
            </div>
          </div>
        </div>
      </article>
      <article className="recovery-card">
        <p className="step-stage">{t.recovery}</p>
        <h3>{t.deliveryTitle}</h3>
        <p>{t.deliveryDetail}</p>
        <div className="recovery-track">
          <span className="recovery-track-stop done">{t.trackEvidence}</span>
          <span className="recovery-track-line" aria-hidden="true" />
          <span className="recovery-track-stop hold">{t.trackReview}</span>
          <span className="recovery-track-line" aria-hidden="true" />
          <span className="recovery-track-stop hold">{t.trackResult}</span>
        </div>
      </article>
      {projection.evidence.kind === "observed" && projection.evidence.value[0] && (
        <article className="blocked-evidence-card">
          <p className="step-stage">{t.evidenceSignal}</p>
          <h3>{projection.evidence.value[0].evidenceId}</h3>
          <p>{projection.evidence.value[0].sourceIdentity}</p>
          <code>{projection.evidence.value[0].fingerprint}</code>
        </article>
      )}
    </div>
  );
}

function diagnosticFailureCause(
  failureCause: Observation<FailureCauseView>,
  language: Language
): string {
  if (failureCause.kind === "observed") {
    return `${failureCause.value.phase} / ${failureCause.value.code}`;
  }
  return observationLabel(failureCause, language);
}

function diagnosticDisposition(projection: ConsoleProjection, language: Language): string {
  if (projection.command.run.kind !== "observed") {
    return copy[language].observations.notObserved;
  }
  return [
    observationLabel(projection.command.run.value.reviewStatus, language),
    observationLabel(projection.command.run.value.deliveryStatus, language)
  ].join(" / ");
}

function JudgmentSidebar({
  isShowcaseRoute,
  language,
  projection,
  showcaseState
}: {
  isShowcaseRoute: boolean;
  language: Language;
  projection: ConsoleProjection;
  showcaseState: ShowcaseState;
}) {
  const t = copy[language];
  const blocked = showcaseState === "blocked";
  const reviewStatus =
    projection.review.status.kind === "observed" ? projection.review.status.value : "not_observed";

  return (
    <aside className="inspector judgment-sidebar">
      <section className="judgment-panel judgment-primary">
        <p className="sidebar-kicker">{t.showcase.judgmentLabel}</p>
        <div className="judgment-heading">
          <h2>{t.labels.review}</h2>
          <span className={`showcase-badge ${blocked ? "blocked" : "ready"}`}>
            {blocked ? t.showcase.judgment.badgeBlocked : t.showcase.judgment.badgeReady}
          </span>
        </div>
        <p>
          {blocked ? t.showcase.blocked.summary : t.showcase.overview.review}
        </p>
      </section>
      <section className="judgment-panel">
        <p className="sidebar-kicker">{t.showcase.judgment.gateChecks}</p>
        <JudgmentRow
          label={t.labels.evidence}
          value={blocked ? t.showcase.judgment.evidenceInsufficient : t.showcase.judgment.evidenceTraceable}
          tone={blocked ? "blocked" : "ready"}
        />
        <JudgmentRow
          label={t.labels.review}
          value={isShowcaseRoute ? reviewStatus : t.showcase.judgment.decisionObserved}
          tone={blocked ? "blocked" : "ready"}
        />
        <JudgmentRow
          label={t.showcase.stages.delivery}
          value={blocked ? t.showcase.blocked.delivery : t.showcase.judgment.badgeReady}
          tone={blocked ? "blocked" : "ready"}
        />
      </section>
      <section className="judgment-panel">
        <p className="sidebar-kicker">{t.showcase.evidence.heading}</p>
        <h3>{t.showcase.judgment.evidenceGateTitle}</h3>
        <p className="sidebar-note">
          {blocked ? t.showcase.blocked.detail : t.showcase.overview.evidence}
        </p>
      </section>

      <details className="technical-disclosure inspector-technical" open={!isShowcaseRoute}>
        <summary>
          <span>{t.labels.authority}</span>
          <small>{t.showcase.technicalDescription}</small>
        </summary>
        <section className="inspector-panel">
          <h2>{t.labels.authority}</h2>
          <ul className="authority-list">
            {authorityBadges.map((badge) => (
              <li key={badge}>{badge}</li>
            ))}
          </ul>
        </section>
        <section className="inspector-panel dark">
          <h2>{t.labels.cli}</h2>
          <pre>{projection.architecture.cliGoldenPath}</pre>
        </section>
        <section className="inspector-panel">
          <h2>{t.labels.boundaries}</h2>
          <p>{t.boundaryStatement}</p>
        </section>
      </details>
    </aside>
  );
}

function LiveJudgmentSidebar({
  language,
  projection
}: {
  language: Language;
  projection: ConsoleProjection;
}) {
  const t = copy[language];
  const deliveryObservation: Observation<string> =
    projection.command.run.kind === "observed"
      ? projection.command.run.value.deliveryStatus
      : { kind: "not_observed" };
  const evidenceStatus =
    projection.evidence.kind === "observed"
      ? `${projection.evidence.value.length} ${t.showcase.live.evidenceObserved}`
      : observationLabel(projection.evidence, language);
  const badge =
    projection.result.kind === "observed"
      ? t.showcase.judgment.badgeObserved
      : t.showcase.judgment.badgeNotObserved;

  return (
    <aside className="inspector judgment-sidebar">
      <section className="judgment-panel judgment-primary">
        <p className="sidebar-kicker">{t.showcase.judgmentLabel}</p>
        <div className="judgment-heading">
          <h2>{t.labels.review}</h2>
          <span className="showcase-badge neutral">{badge}</span>
        </div>
        <p>{t.showcase.judgment.liveSummary}</p>
      </section>
      <section className="judgment-panel">
        <p className="sidebar-kicker">{t.showcase.judgment.gateChecks}</p>
        <JudgmentRow label={t.labels.evidence} value={evidenceStatus} tone="neutral" />
        <JudgmentRow
          label={t.labels.review}
          value={observationLabel(projection.review.status, language)}
          tone="neutral"
        />
        <JudgmentRow
          label={t.showcase.stages.delivery}
          value={observationLabel(deliveryObservation, language)}
          tone="neutral"
        />
      </section>
      <section className="judgment-panel">
        <p className="sidebar-kicker">{t.showcase.evidence.heading}</p>
        <h3>{t.showcase.judgment.evidenceGateTitle}</h3>
        <p className="sidebar-note">{t.showcase.judgment.liveSummary}</p>
      </section>

      <details className="technical-disclosure inspector-technical" open>
        <summary>
          <span>{t.labels.authority}</span>
          <small>{t.showcase.technicalDescription}</small>
        </summary>
        <section className="inspector-panel">
          <h2>{t.labels.authority}</h2>
          <ul className="authority-list">
            {authorityBadges.map((badge) => (
              <li key={badge}>{badge}</li>
            ))}
          </ul>
        </section>
        <section className="inspector-panel dark">
          <h2>{t.labels.cli}</h2>
          <pre>{projection.architecture.cliGoldenPath}</pre>
        </section>
        <section className="inspector-panel">
          <h2>{t.labels.boundaries}</h2>
          <p>{t.boundaryStatement}</p>
        </section>
      </details>
    </aside>
  );
}

function JudgmentRow({
  label,
  tone,
  value
}: {
  label: string;
  tone: "blocked" | "neutral" | "ready";
  value: string;
}) {
  return (
    <div className="judgment-row">
      <span>{label}</span>
      <strong className={tone}>{value}</strong>
    </div>
  );
}

function LiveDemoPanel({
  language,
  liveRun,
  projection
}: {
  language: Language;
  liveRun: ReturnType<typeof useLiveRun>;
  projection: ConsoleProjection;
}) {
  const t = copy[language];
  const { state } = liveRun;
  const isLive = state.mode === "live";
  const isBusy = ["checking", "creating", "polling"].includes(state.status);
  const requiresRecovery = ["reconciliation_required", "observation_interrupted"].includes(
    state.status
  );
  const hasKnownRunError = state.status === "error" && Boolean(state.error?.run_id);
  const [queryDraft, setQueryDraft] = useState(DEFAULT_LIVE_DEMO_QUERY);
  const queryValidation = validateLiveDemoQuery(queryDraft);
  const queryLocked =
    !isLive ||
    ["creating", "polling", "reconciliation_required", "observation_interrupted"].includes(
      state.status
    ) ||
    hasKnownRunError;
  const queryDescribedBy = [
    "live-query-hint",
    "live-query-bytes",
    ...(queryValidation.ok ? [] : ["live-query-feedback"])
  ].join(" ");
  const canStartNewRun =
    isLive && queryValidation.ok && ["ready", "terminal", "result"].includes(state.status);

  return (
    <section className="live-panel" aria-label={t.live.status}>
      <div className="mode-switch" aria-label={t.labels.mode}>
        <button
          className={state.mode === "static" ? "active" : ""}
          disabled={state.mode === "static"}
          type="button"
          onClick={() => liveRun.setMode("static")}
        >
          {t.live.staticMode}
        </button>
        <button
          className={isLive ? "active" : ""}
          disabled={isLive}
          type="button"
          onClick={() => liveRun.setMode("live")}
        >
          {t.live.liveMode}
        </button>
      </div>

      <div className="live-controls">
        <label>
          <span>{t.live.baseUrl}</span>
          <input
            aria-label={t.live.baseUrl}
            disabled={!isLive || isBusy}
            value={state.baseUrl}
            onChange={(event) => liveRun.setBaseUrl(event.target.value)}
          />
        </label>
        <div className="live-query-field">
          <label htmlFor="live-research-question">{t.live.question}</label>
          <textarea
            aria-describedby={queryDescribedBy}
            aria-invalid={queryValidation.ok ? "false" : "true"}
            disabled={queryLocked}
            id="live-research-question"
            rows={4}
            value={queryDraft}
            onChange={(event) => setQueryDraft(event.target.value)}
          />
          <small id="live-query-hint">{t.live.questionHint}</small>
          <small className="live-query-bytes" id="live-query-bytes">
            {t.live.queryBytes(queryValidation.utf8Bytes)}
          </small>
          {!queryValidation.ok && (
            <p className="live-query-feedback" id="live-query-feedback">
              {queryValidation.reason === "blank" ? t.live.queryBlank : t.live.queryTooLarge}
            </p>
          )}
        </div>
        <button
          disabled={!isLive || isBusy || requiresRecovery || hasKnownRunError}
          type="button"
          onClick={liveRun.checkHealth}
        >
          {t.live.checkHealth}
        </button>
        <button
          disabled={!canStartNewRun}
          type="button"
          onClick={() => liveRun.startNewRun(queryDraft)}
        >
          {t.live.runResult}
        </button>
        {state.status === "reconciliation_required" && (
          <div className="recovery-actions">
            <button type="button" onClick={liveRun.retryCreate}>
              {t.live.retrySameRequest}
            </button>
            <button type="button" onClick={liveRun.discardPendingIntent}>
              {t.live.discardPendingRequest}
            </button>
          </div>
        )}
        {state.status === "observation_interrupted" && (
          <div className="recovery-actions">
            <button type="button" onClick={liveRun.resumeObservation}>
              {t.live.resumeObservation}
            </button>
          </div>
        )}
      </div>

      <div className="live-status-grid">
        <article>
          <strong>{state.mode === "static" ? t.live.staticDescription : t.live.liveDescription}</strong>
          <p>{state.status === "ready" ? t.live.backendAvailable : t.live.statuses[state.status]}</p>
        </article>
        {projection.source === "live" && projection.command.create.kind === "observed" && (
          <article>
            <strong>run_id</strong>
            <p>{projection.command.create.value.runId}</p>
            <small>
              {projection.command.create.value.idempotentReplay
                ? t.live.replayReceipt
                : t.live.originalReceipt}
            </small>
          </article>
        )}
        {state.error && <LiveErrorCard error={state.error} fallbackFix={t.live.startBackend} />}
        {projection.source === "live" && projection.result.kind === "observed" ? (
          <article className="live-result-card">
            <strong>{t.live.resultPreview}</strong>
            <p>{projection.result.value.artifact.artifactId}</p>
            <pre>{projection.result.value.artifact.content}</pre>
          </article>
        ) : (
          <article>
            <strong>{t.live.resultPreview}</strong>
            <p>{t.live.noResult}</p>
          </article>
        )}
      </div>
    </section>
  );
}

function LiveErrorCard({ error, fallbackFix }: { error: ClientError; fallbackFix: string }) {
  const fix = error.code === "connection_failed" ? fallbackFix : error.fix || fallbackFix;
  return (
    <article className="live-error-card">
      <strong>{error.code}</strong>
      <p>{error.problem}</p>
      <small>{fix}</small>
      {error.run_id && <code>{error.run_id}</code>}
    </article>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <article className={`metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function CommandCenter({
  language,
  projection
}: {
  language: Language;
  projection: ConsoleProjection;
}) {
  const t = copy[language];
  return (
    <div className="command-grid">
      <div className="flow-map">
        <div className="caller-row">
          {["OpenClaw", "Codex", "Tool Client", "REST caller"].map((caller) => (
            <span className="caller" key={caller}>
              {caller}
            </span>
          ))}
        </div>
        <span className="flow-connector" aria-hidden="true">↓</span>
        <div className="execution-path">
          <span className="node">FastAPI</span>
          <span className="arrow">→</span>
          <span className="node">ResearchExecutionService</span>
          <span className="arrow">→</span>
          <span className="node">DeepAgentsHarness</span>
        </div>
        <div className="authority-row">
          <span className="flow-connector" aria-hidden="true">↳</span>
          <span className="node authority">Application DB authority</span>
        </div>
        <p className="note">
          {t.labels.authority}: Application DB = business authority; LangSmith = diagnostics only.
        </p>
      </div>

      <div className="projection-stack">
        <h3>{projection.source === "static" ? t.projection.staticSnapshot : t.projection.liveProjection}</h3>
        <ObservationSection
          language={language}
          observation={projection.command.create}
          title={t.projection.createReceipt}
          render={(receipt) => (
            <KeyValueList
              entries={[
                ["run_id", receipt.runId],
                ["thread_id", receipt.threadId],
                ["segment_id", receipt.segmentId],
                ["status", receipt.status],
                ["idempotent_replay", String(receipt.idempotentReplay)]
              ]}
            />
          )}
        />
        <ObservationSection
          language={language}
          observation={projection.command.run}
          title={t.projection.runState}
          render={(run) => (
            <KeyValueList
              entries={[
                ["run_id", run.runId],
                ["thread_id", run.threadId],
                ["profile_id", run.profileId],
                ["state_version", String(run.stateVersion)],
                ["execution_status", <ObservationValue language={language} observation={run.executionStatus} />],
                ["review_status", <ObservationValue language={language} observation={run.reviewStatus} />],
                ["delivery_status", <ObservationValue language={language} observation={run.deliveryStatus} />]
              ]}
            />
          )}
        />
        <ObservationSection
          language={language}
          observation={projection.command.publication}
          title={t.projection.publication}
          render={(publication) => (
            <KeyValueList
              entries={[
                ["publication_id", publication.publicationId],
                ["revision", String(publication.revision)],
                ["status", publication.status],
                ["artifact_ids", publication.artifactIds.join(", ") || t.observations.observedEmptyCollection]
              ]}
            />
          )}
        />
        <ObservationSection
          language={language}
          observation={projection.command.artifacts}
          title={t.projection.artifacts}
          render={(artifacts) =>
            artifacts.length === 0 ? (
              <p className="observation observed-empty">{t.observations.observedEmptyCollection}</p>
            ) : (
              <ul className="projection-list">
                {artifacts.map((artifact) => (
                  <li key={artifact.artifactId}>
                    <strong>{artifact.artifactId}</strong>
                    <span>{artifact.mediaType}</span>
                    <code>{artifact.contentHash}</code>
                  </li>
                ))}
              </ul>
            )
          }
        />
      </div>
    </div>
  );
}

function RunLifecycle({
  language,
  projection
}: {
  language: Language;
  projection: ConsoleProjection;
}) {
  const t = copy[language];
  const lifecycle = projection.lifecycle;
  return (
    <div className="two-column">
      <section>
        <h3>{lifecycle.kind === "event_history" ? t.projection.eventHistory : t.projection.stateProjection}</h3>
        {lifecycle.entries.kind === "observed" ? (
          lifecycle.entries.value.length === 0 ? (
            <p className="observation observed-empty">{t.observations.observedEmptyCollection}</p>
          ) : (
            <ol className="run-spine">
              {lifecycle.entries.value.map((entry, index) => (
                <li key={`${entry.category}-${entry.label}-${index}`}>
                  <strong>{entry.label}</strong>
                  {entry.segmentKind && <span>{entry.segmentKind}</span>}
                  <span>
                    status: <ObservationValue language={language} observation={entry.status} />
                  </span>
                  <span>
                    sequence: <ObservationValue language={language} observation={entry.sequence} />
                  </span>
                  <span>
                    attempt: <ObservationValue language={language} observation={entry.attempt} />
                  </span>
                </li>
              ))}
            </ol>
          )
        ) : (
          <ObservationValue language={language} observation={lifecycle.entries} />
        )}
      </section>
      <ObservationSection
        language={language}
        observation={lifecycle.failureCause}
        title={t.projection.failureCause}
        render={(failureCause) => (
          <KeyValueList
            entries={[
              ["schema_version", failureCause.schemaVersion],
              ["phase", failureCause.phase],
              ["code", failureCause.code],
              ["recorded_at", failureCause.recordedAt]
            ]}
          />
        )}
      />
    </div>
  );
}

function EvidenceLedger({
  language,
  projection
}: {
  language: Language;
  projection: ConsoleProjection;
}) {
  const t = copy[language];
  if (projection.evidence.kind !== "observed") {
    return (
      <article className="observation-card">
        <ObservationValue language={language} observation={projection.evidence} />
      </article>
    );
  }
  if (projection.evidence.value.length === 0) {
    return <p className="observation observed-empty">{t.observations.observedEmptyEvidence}</p>;
  }
  return (
    <div className="evidence-grid">
      {projection.evidence.value.map((entry) => (
        <article className="evidence-card" key={entry.evidenceId}>
          <header>
            <strong>{entry.evidenceId}</strong>
            <span>{entry.verificationStatus}</span>
          </header>
          <p>{entry.sourceIdentity}</p>
          <p>
            source_url: <ObservationValue language={language} observation={entry.sourceUrl} />
          </p>
          <p>
            citation_status: <ObservationValue language={language} observation={entry.citationStatus} />
          </p>
          <code>{entry.fingerprint}</code>
          {entry.citedBy.kind === "observed" && (
            <div className="chips" aria-label={t.labels.citedBy}>
              {entry.citedBy.value.map((claim) => (
                <span key={claim}>{claim}</span>
              ))}
            </div>
          )}
        </article>
      ))}
    </div>
  );
}

function ReviewVerification({
  language,
  projection
}: {
  language: Language;
  projection: ConsoleProjection;
}) {
  const t = copy[language];
  const review = projection.review;
  return (
    <div className="two-column">
      <div className="projection-stack">
        <article className="ledger-card">
          <h3>{t.labels.review}</h3>
          <KeyValueList
            entries={[
              ["status", <ObservationValue language={language} observation={review.status} />],
              ["decision_id", <ObservationValue language={language} observation={review.decisionId} />],
              ["state_version", <ObservationValue language={language} observation={review.stateVersion} />],
              ["idempotency", <ObservationValue language={language} observation={review.idempotency} />]
            ]}
          />
        </article>
        <ObservationSection
          language={language}
          observation={review.workflow}
          title={t.projection.workflow}
          render={(workflow) => (
            <KeyValueList
              entries={[
                ["workflow_id", workflow.workflow_id],
                ["review_id", workflow.review_id],
                ["status", workflow.status],
                ["decision_id", workflow.decision_id ?? t.observations.notApplicable]
              ]}
            />
          )}
        />
        <ObservationSection
          language={language}
          observation={review.decision}
          title={t.projection.decision}
          render={(decision) => (
            <KeyValueList
              entries={[
                ["decision_id", decision.decision_id],
                ["review_id", decision.review_id],
                ["action", decision.action],
                ["accepted_state_version", String(decision.accepted_state_version)]
              ]}
            />
          )}
        />
        <ObservationSection
          language={language}
          observation={review.resolution}
          title={t.projection.resolution}
          render={(resolution) => (
            <KeyValueList
              entries={[
                ["resolution_id", resolution.resolution_id],
                ["decision_id", resolution.decision_id],
                ["action", resolution.action],
                ["artifact_ids", resolution.artifact_ids.join(", ") || t.observations.observedEmptyCollection]
              ]}
            />
          )}
        />
      </div>
      <ObservationSection
        language={language}
        observation={projection.verification}
        title={t.labels.verification}
        render={(verification) =>
          verification.source === "static" ? (
            <KeyValueList
              entries={[
                ["snapshot", verification.snapshot],
                ["origin", verification.baselineOrigin],
                ["status", verification.status],
                ["publication", verification.publicationFreshness]
              ]}
            />
          ) : (
            <KeyValueList
              entries={[
                ["state_counts", countSummary(verification.stateCounts)],
                ["origin_counts", countSummary(verification.originCounts)],
                ["snapshot_hash", verification.snapshotHash ?? t.observations.notApplicable]
              ]}
            />
          )
        }
      />
    </div>
  );
}

function CanonicalResult({
  language,
  projection
}: {
  language: Language;
  projection: ConsoleProjection;
}) {
  const t = copy[language];
  if (projection.result.kind === "observed") {
    const result = projection.result.value;
    return (
      <div className="result-layout">
        <article className="ledger-card">
          <h3>{t.labels.artifact}</h3>
          <KeyValueList
            entries={[
              ["run_id", result.runId],
              ["artifact_id", result.artifact.artifactId],
              ["kind", <ObservationValue language={language} observation={result.artifact.kind} />],
              ["media_type", result.artifact.mediaType],
              ["content_hash", result.artifact.contentHash],
              ["revision", <ObservationValue language={language} observation={result.artifact.revision} />],
              ["safety", <ObservationValue language={language} observation={result.artifact.safety} />]
            ]}
          />
        </article>
        <article className="markdown-preview">
          <pre>{result.artifact.content}</pre>
        </article>
      </div>
    );
  }
  if (projection.result.kind === "not_applicable") {
    return (
      <article className="ledger-card terminal-card">
        <h3>{t.observations.terminalNoResult}</h3>
        {projection.lifecycle.run.kind === "observed" && (
          <KeyValueList
            entries={[
              ["run_id", projection.lifecycle.run.value.runId],
              [
                "execution_status",
                <ObservationValue
                  language={language}
                  observation={projection.lifecycle.run.value.executionStatus}
                />
              ],
              [
                "delivery_status",
                <ObservationValue
                  language={language}
                  observation={projection.lifecycle.run.value.deliveryStatus}
                />
              ]
            ]}
          />
        )}
      </article>
    );
  }
  return (
    <article className="observation-card">
      <ObservationValue language={language} observation={projection.result} />
    </article>
  );
}

function ArchitectureMode({
  language,
  projection
}: {
  language: Language;
  projection: ConsoleProjection;
}) {
  const t = copy[language];
  return (
    <div>
      <h3>{t.labels.authority}</h3>
      <p className="observation unsupported">{t.observations.referenceOnly}</p>
      <ol className="architecture-flow">
        {projection.architecture.nodes.map((node) => (
          <li key={node}>{node}</li>
        ))}
      </ol>
    </div>
  );
}

function ObservationSection<T>({
  language,
  observation,
  render,
  title
}: {
  language: Language;
  observation: Observation<T>;
  render: (value: T) => ReactNode;
  title: string;
}) {
  return (
    <article className="ledger-card observation-card">
      <h3>{title}</h3>
      {observation.kind === "observed" ? (
        render(observation.value)
      ) : (
        <ObservationValue language={language} observation={observation} />
      )}
    </article>
  );
}

function ObservationValue<T>({
  language,
  observation
}: {
  language: Language;
  observation: Observation<T>;
}) {
  return (
    <span className={`observation ${observation.kind}`}>
      {observationLabel(observation, language)}
    </span>
  );
}

function observationLabel<T>(observation: Observation<T>, language: Language): string {
  if (observation.kind === "observed") {
    return String(observation.value);
  }
  const labels = copy[language].observations;
  switch (observation.kind) {
    case "not_observed":
      return labels.notObserved;
    case "not_applicable":
      return labels.notApplicable;
    case "unsupported":
      return labels.unsupported;
  }
}

function KeyValueList({ entries }: { entries: Array<[string, ReactNode]> }) {
  return (
    <dl>
      {entries.map(([label, value], index) => (
        <div className="definition-row" key={`${label}-${index}`}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function countSummary(counts: Readonly<Record<string, number>>) {
  const entries = Object.entries(counts);
  return entries.length === 0
    ? "{}"
    : entries.map(([key, value]) => `${key}: ${value}`).join(", ");
}

function buildScreenSummary(screen: ScreenKey) {
  const summaries: Record<ScreenKey, string> = {
    command: "research operations",
    lifecycle: "run-scoped",
    evidence: "append-only",
    review: "human-governed",
    result: "canonical endpoint",
    architecture: "boundary map"
  };

  return summaries[screen];
}
