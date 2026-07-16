import { type ReactNode, useEffect, useMemo, useState } from "react";

import type { ClientError } from "./apiClient";
import {
  buildLiveConsoleProjection,
  buildStaticConsoleProjection,
  type ConsoleProjection,
  type Observation
} from "./consoleProjection";
import { copy, type Language, screenEnglishNames, screenKeys, type ScreenKey } from "./i18n";
import { type LiveRunOptions, useLiveRun } from "./useLiveRun";

const authorityBadges = [
  "Application DB",
  "LangGraph checkpoint",
  "LangSmith diagnostics",
  "GET /api/runs/{run_id}/result"
];

export default function App({ liveOptions }: { liveOptions?: LiveRunOptions }) {
  const [language, setLanguage] = useState<Language>("zh");
  const [activeScreen, setActiveScreen] = useState<ScreenKey>("command");
  const liveRun = useLiveRun(liveOptions);
  const t = copy[language];
  const projection = useMemo(
    () =>
      liveRun.state.mode === "static"
        ? buildStaticConsoleProjection()
        : buildLiveConsoleProjection({
            health: liveRun.state.health,
            created: liveRun.state.created,
            run: liveRun.state.run,
            result: liveRun.state.result,
            status: liveRun.state.status
          }),
    [liveRun.state]
  );

  const activeTitle = t.screens[activeScreen];
  const activeStatement = t.statements[activeScreen];
  const screenSummary = useMemo(() => buildScreenSummary(activeScreen), [activeScreen]);

  useEffect(() => {
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  }, [language]);

  return (
    <div className="console-shell">
      <header className="top-bar">
        <div>
          <p className="eyebrow">{t.eyebrow}</p>
          <h1>{activeTitle}</h1>
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
        <aside className="left-rail">
          <nav aria-label={t.navLabel}>
            {screenKeys.map((screenKey) => (
              <button
                aria-label={screenEnglishNames[screenKey]}
                className={screenKey === activeScreen ? "nav-item active" : "nav-item"}
                key={screenKey}
                type="button"
                onClick={() => setActiveScreen(screenKey)}
              >
                <span>{t.screens[screenKey]}</span>
                <small>{screenEnglishNames[screenKey]}</small>
              </button>
            ))}
          </nav>
        </aside>

        <main className={`canvas ${liveRun.state.mode}-mode`}>
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

          <LiveDemoPanel language={language} liveRun={liveRun} projection={projection} />
        </main>

        <aside className="inspector">
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
        </aside>
      </div>
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
  const canStartNewRun =
    isLive && ["ready", "terminal", "result"].includes(state.status);

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
        <button
          disabled={!isLive || isBusy || requiresRecovery || hasKnownRunError}
          type="button"
          onClick={liveRun.checkHealth}
        >
          {t.live.checkHealth}
        </button>
        <button disabled={!canStartNewRun} type="button" onClick={liveRun.startNewRun}>
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
