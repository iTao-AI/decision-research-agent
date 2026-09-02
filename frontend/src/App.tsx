import { useEffect, useMemo, useState } from "react";

import {
  DEFAULT_LIVE_DEMO_QUERY,
  type ClientError,
  validateLiveDemoQuery,
  validateLiveRunId
} from "./apiClient";
import {
  buildLiveConsoleProjection,
  buildStaticConsoleProjection,
  type ConsoleProjection,
  type StaticShowcaseScenario
} from "./consoleProjection";
import { copy, type Language, screenEnglishNames, type ScreenKey } from "./i18n";
import { type LiveRunOptions, useLiveRun } from "./useLiveRun";
import { JudgmentSidebar, LiveJudgmentSidebar } from "./presentation/judgmentSidebar";
import { initialScreenForShowcase, StageRail } from "./presentation/stageRail";
import { LiveObservationSurface, ShowcaseWorkspace, type ShowcaseState } from "./presentation/showcaseWorkspace";
import {
  ArchitectureMode,
  CanonicalResult,
  CommandCenter,
  EvidenceLedger,
  Metric,
  ReviewVerification,
  RunLifecycle
} from "./presentation/technicalScreens";
import { buildScreenSummary, ObservationValue, observationLabel } from "./presentation/observation";

export type { ShowcaseState } from "./presentation/showcaseWorkspace";

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
    isShowcaseRoute ? initialScreenForShowcase(showcaseState) : "command"
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
  const [knownRunDraft, setKnownRunDraft] = useState("");
  const queryValidation = validateLiveDemoQuery(queryDraft);
  const knownRunValidation = validateLiveRunId(knownRunDraft);
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
  const knownRunLocked =
    !isLive ||
    !state.health ||
    ["checking", "creating", "polling", "reconciliation_required", "observation_interrupted"].includes(
      state.status
    ) ||
    (state.status === "error" && !hasKnownRunError) ||
    !["ready", "terminal", "result", "error"].includes(state.status);
  const knownRunHasValidationError = knownRunDraft.length > 0 && !knownRunValidation.ok;
  const knownRunDescribedBy = [
    "live-known-run-hint",
    ...(knownRunHasValidationError ? ["live-known-run-feedback"] : [])
  ].join(" ");
  const canObserveKnownRun = !knownRunLocked && knownRunValidation.ok;

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
        <div className="live-known-run-field">
          <label htmlFor="live-known-run">{t.live.knownRun}</label>
          <input
            aria-describedby={knownRunDescribedBy}
            aria-invalid={knownRunHasValidationError ? "true" : "false"}
            disabled={knownRunLocked}
            id="live-known-run"
            value={knownRunDraft}
            onChange={(event) => setKnownRunDraft(event.target.value)}
          />
          <small id="live-known-run-hint">{t.live.knownRunHint}</small>
          {knownRunHasValidationError && (
            <p className="live-known-run-feedback" id="live-known-run-feedback">
              {knownRunValidation.reason === "blank"
                ? t.live.knownRunBlank
                : knownRunValidation.reason === "too_long"
                  ? t.live.knownRunTooLong
                  : t.live.knownRunInvalidFormat}
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
        <button
          disabled={!canObserveKnownRun}
          type="button"
          onClick={() => liveRun.attachKnownRun(knownRunDraft)}
        >
          {t.live.observeKnownRun}
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
