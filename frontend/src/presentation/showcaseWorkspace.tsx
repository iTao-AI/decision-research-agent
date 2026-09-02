import {
  type ConsoleProjection,
  type FailureCauseView,
  type Observation
} from "../consoleProjection";
import { copy, type Language } from "../i18n";
import { ObservationValue, observationLabel } from "./observation";

export type ShowcaseState = "overview" | "evidence" | "blocked";

export function ShowcaseWorkspace({
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

export function LiveObservationSurface({
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
