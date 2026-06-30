import { useEffect, useMemo, useState } from "react";

import { architectureNodes, demoRun } from "./demoData";
import { copy, type Language, screenEnglishNames, screenKeys, type ScreenKey } from "./i18n";
import { type ClientError, type RunResultResponse } from "./apiClient";
import { type DemoMode, type LiveRunOptions, type LiveRunState, useLiveRun } from "./useLiveRun";

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

  const activeTitle = t.screens[activeScreen];
  const activeStatement = t.statements[activeScreen];
  const screenSummary = useMemo(() => buildScreenSummary(activeScreen), [activeScreen]);
  const displayRunId = liveRun.state.created?.run_id ?? liveRun.state.result?.run_id ?? demoRun.runId;
  const displayService = liveRun.state.health?.service ?? demoRun.service;
  const displayHealth = liveRun.state.health?.status ?? liveRun.state.status;
  const displayMode = liveRun.state.mode === "static" ? demoRun.mode : "live backend";

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
            {screenKeys.map((screen) => (
              <button
                aria-label={screenEnglishNames[screen]}
                className={screen === activeScreen ? "nav-item active" : "nav-item"}
                key={screen}
                type="button"
                onClick={() => setActiveScreen(screen)}
              >
                <span>{t.screens[screen]}</span>
                <small>{screenEnglishNames[screen]}</small>
              </button>
            ))}
          </nav>
        </aside>

        <main className={`canvas ${liveRun.state.mode}-mode`}>
          <section className="status-grid" aria-label="Run state summary">
            <Metric label={t.labels.service} value={displayService} tone="blue" />
            <Metric label={t.labels.health} value={displayHealth} tone="amber" />
            <Metric label={t.labels.mode} value={displayMode} tone="cyan" />
            <Metric label={t.labels.run} value={displayRunId} tone="green" />
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

            {activeScreen === "command" && <CommandCenter labels={t.labels} />}
            {activeScreen === "lifecycle" && <RunLifecycle labels={t.labels} />}
            {activeScreen === "evidence" && <EvidenceLedger labels={t.labels} />}
            {activeScreen === "review" && <ReviewVerification labels={t.labels} />}
            {activeScreen === "result" && <CanonicalResult labels={t.labels} />}
            {activeScreen === "architecture" && <ArchitectureMode labels={t.labels} />}
          </section>

          <LiveDemoPanel
            language={language}
            liveRun={liveRun}
          />
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
            <pre>{demoRun.cliGoldenPath}</pre>
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
  liveRun
}: {
  language: Language;
  liveRun: {
    checkHealth: () => Promise<void>;
    runGoldenPath: () => Promise<void>;
    setBaseUrl: (baseUrl: string) => void;
    setMode: (mode: DemoMode) => void;
    state: LiveRunState;
  };
}) {
  const t = copy[language];
  const { state } = liveRun;
  const isLive = state.mode === "live";
  const isBusy = ["checking", "starting", "polling"].includes(state.status);
  return (
    <section className="live-panel" aria-label={t.live.status}>
      <div className="mode-switch" aria-label={t.labels.mode}>
        <button
          className={state.mode === "static" ? "active" : ""}
          type="button"
          onClick={() => liveRun.setMode("static")}
        >
          {t.live.staticMode}
        </button>
        <button
          className={isLive ? "active" : ""}
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
        <button disabled={!isLive || isBusy} type="button" onClick={liveRun.checkHealth}>
          {t.live.checkHealth}
        </button>
        <button
          disabled={!isLive || isBusy || state.status === "idle" || state.status === "error"}
          type="button"
          onClick={liveRun.runGoldenPath}
        >
          {t.live.runResult}
        </button>
      </div>

      <div className="live-status-grid">
        <article>
          <strong>{state.mode === "static" ? t.live.staticDescription : t.live.liveDescription}</strong>
          <p>{state.status === "ready" ? t.live.backendAvailable : t.live.statuses[state.status]}</p>
        </article>
        {state.created && (
          <article>
            <strong>run_id</strong>
            <p>{state.created.run_id}</p>
          </article>
        )}
        {state.error && <LiveErrorCard error={state.error} fallbackFix={t.live.startBackend} />}
        {state.result ? (
          <article className="live-result-card">
            <strong>{t.live.resultPreview}</strong>
            <p>{state.result.artifact?.artifact_id ?? "unknown artifact"}</p>
            <pre>{resultPreview(state.result)}</pre>
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

function resultPreview(result: RunResultResponse) {
  const content = result.artifact?.content;
  if (typeof content === "string" && content.trim()) {
    return content;
  }
  return JSON.stringify(result, null, 2);
}

function Metric({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <article className={`metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function CommandCenter({ labels }: { labels: Record<string, string> }) {
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
          {labels.authority}: Application DB = business authority; LangSmith = diagnostics only.
        </p>
      </div>

      <article className="ledger-card">
        <h3>Static demo snapshot</h3>
        <dl>
          <dt>run_id</dt>
          <dd>{demoRun.runId}</dd>
          <dt>lifecycle</dt>
          <dd>{demoRun.lifecycle.join(" -> ")}</dd>
          <dt>evidence</dt>
          <dd>{demoRun.evidence.map((entry) => entry.id).join(", ")}</dd>
          <dt>claim refs</dt>
          <dd>{demoRun.evidence.flatMap((entry) => entry.citedBy).join(", ")}</dd>
          <dt>review</dt>
          <dd>{demoRun.review.status}</dd>
          <dt>verification</dt>
          <dd>{demoRun.verification.status}</dd>
          <dt>result</dt>
          <dd>{demoRun.artifact.id}</dd>
        </dl>
      </article>
    </div>
  );
}

function RunLifecycle({ labels }: { labels: Record<string, string> }) {
  return (
    <div className="two-column">
      <div>
        <h3>{labels.lifecycle}</h3>
        <ol className="run-spine">
          {demoRun.lifecycle.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
      </div>
      <div>
        <h3>{labels.telemetry}</h3>
        <ul className="event-list">
          {demoRun.telemetry.map((event) => (
            <li key={event}>{event}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function EvidenceLedger({ labels }: { labels: Record<string, string> }) {
  return (
    <div className="evidence-grid">
      {demoRun.evidence.map((entry) => (
        <article className="evidence-card" key={entry.id}>
          <header>
            <strong>{entry.id}</strong>
            <span>{entry.verification}</span>
          </header>
          <p>{entry.source}</p>
          <code>{entry.fingerprint}</code>
          <div className="chips" aria-label={labels.citedBy}>
            {entry.citedBy.map((claim) => (
              <span key={claim}>{claim}</span>
            ))}
          </div>
        </article>
      ))}
    </div>
  );
}

function ReviewVerification({ labels }: { labels: Record<string, string> }) {
  return (
    <div className="two-column">
      <article className="ledger-card">
        <h3>{labels.review}</h3>
        <dl>
          <dt>Status</dt>
          <dd>{demoRun.review.status}</dd>
          <dt>Decision</dt>
          <dd>{demoRun.review.decisionId}</dd>
          <dt>state_version</dt>
          <dd>{demoRun.review.stateVersion}</dd>
          <dt>Idempotency</dt>
          <dd>{demoRun.review.idempotency}</dd>
        </dl>
      </article>
      <article className="ledger-card">
        <h3>{labels.verification}</h3>
        <dl>
          <dt>Snapshot</dt>
          <dd>{demoRun.verification.snapshot}</dd>
          <dt>Origin</dt>
          <dd>{demoRun.verification.baselineOrigin}</dd>
          <dt>Status</dt>
          <dd>{demoRun.verification.status}</dd>
          <dt>Publication</dt>
          <dd>{demoRun.verification.publicationFreshness}</dd>
        </dl>
      </article>
    </div>
  );
}

function CanonicalResult({ labels }: { labels: Record<string, string> }) {
  return (
    <div className="result-layout">
      <article className="ledger-card">
        <h3>{labels.artifact}</h3>
        <dl>
          <dt>artifact_id</dt>
          <dd>{demoRun.artifact.id}</dd>
          <dt>media_type</dt>
          <dd>{demoRun.artifact.mediaType}</dd>
          <dt>revision</dt>
          <dd>{demoRun.artifact.revision}</dd>
          <dt>content_hash</dt>
          <dd>{demoRun.artifact.contentHash}</dd>
          <dt>safety</dt>
          <dd>{demoRun.artifact.safety}</dd>
        </dl>
      </article>
      <article className="markdown-preview">
        <pre>{demoRun.resultMarkdown}</pre>
      </article>
    </div>
  );
}

function ArchitectureMode({ labels }: { labels: Record<string, string> }) {
  return (
    <div>
      <h3>{labels.authority}</h3>
      <ol className="architecture-flow">
        {architectureNodes.map((node) => (
          <li key={node}>{node}</li>
        ))}
      </ol>
    </div>
  );
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
