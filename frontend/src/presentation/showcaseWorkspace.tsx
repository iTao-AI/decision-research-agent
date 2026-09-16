import { useEffect } from "react";

import { researchBriefFixture } from "../demoData";
import {
  type ConsoleProjection,
  type FailureCauseView,
  type Observation
} from "../consoleProjection";
import { copy, type Language } from "../i18n";
import { ObservationValue, observationLabel } from "./observation";
import {
  type EvidenceSelection,
  LiveEvidenceSourcePanel,
  StaticEvidenceSourcePanel
} from "./evidenceSourcePanel";
import { ResultReader } from "./resultReader";

export type ShowcaseState = "overview" | "evidence" | "blocked";

export function ShowcaseWorkspace({
  language,
  projection,
  showcaseState,
  selection,
  onReturnToClaim,
  onSelectEvidence
}: {
  language: Language;
  projection: ConsoleProjection;
  showcaseState: ShowcaseState;
  selection: EvidenceSelection;
  onReturnToClaim: (claimId: string) => void;
  onSelectEvidence: (evidenceId: string, claimId?: string) => void;
}) {
  if (showcaseState === "blocked") {
    return <BlockedShowcase language={language} projection={projection} />;
  }
  if (showcaseState === "evidence") {
    return (
      <EvidenceShowcase
        language={language}
        projection={projection}
        selection={selection}
        onSelectEvidence={onSelectEvidence}
      />
    );
  }
  return (
    <OverviewShowcase
      language={language}
      projection={projection}
      selection={selection}
      onSelectEvidence={onSelectEvidence}
    />
  );
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
      </div>
      <ResultReader language={language} mode="live" result={projection.result} />
    </section>
  );
}

type ResearchBriefShowcaseProps = {
  language: Language;
  projection: ConsoleProjection;
  selection: EvidenceSelection;
  onSelectEvidence: (evidenceId: string, claimId?: string) => void;
  showcaseState: ShowcaseState;
};

function OverviewShowcase({
  language,
  projection,
  selection,
  onSelectEvidence
}: Omit<ResearchBriefShowcaseProps, "showcaseState">) {
  return (
    <ResearchBriefShowcase
      language={language}
      projection={projection}
      showcaseState="overview"
      selection={selection}
      onSelectEvidence={onSelectEvidence}
    />
  );
}

function EvidenceShowcase({
  language,
  projection,
  selection,
  onSelectEvidence
}: Omit<ResearchBriefShowcaseProps, "showcaseState">) {
  return (
    <ResearchBriefShowcase
      language={language}
      projection={projection}
      showcaseState="evidence"
      selection={selection}
      onSelectEvidence={onSelectEvidence}
    />
  );
}

function ResearchBriefShowcase({
  language,
  projection,
  showcaseState,
  selection,
  onSelectEvidence
}: ResearchBriefShowcaseProps) {
  const t = copy[language];

  useEffect(() => {
    if (selection.focus !== "claim" || !selection.claimId) {
      return;
    }
    const claim = document.getElementById(`research-claim-${selection.claimId}`);
    if (claim instanceof HTMLElement) {
      claim.focus();
      claim.scrollIntoView?.({ block: "center" });
    }
  }, [selection.claimId, selection.focus]);

  return (
    <div className={`brief-workspace ${showcaseState === "evidence" ? "brief-evidence-route" : ""}`}>
      <section className="brief-report-intro">
        <div className="brief-disclosure">
          <span className="brief-disclosure-mark">i</span>
          <p>{researchBriefFixture.disclosure}</p>
        </div>
        <article className="recommendation-block">
          <p className="step-stage">{t.showcase.brief.recommendationLabel}</p>
          <h3>{researchBriefFixture.recommendation}</h3>
          <p>{researchBriefFixture.recommendationDetail}</p>
        </article>
      </section>

      <ResultReader language={language} mode="static" result={projection.result} />

      <section className="comparison-section" aria-labelledby="comparison-heading">
        <div className="section-heading-row">
          <div>
            <p className="step-stage">{t.showcase.brief.criteriaLabel}</p>
            <h3 id="comparison-heading">{t.showcase.brief.criteriaLabel}</h3>
          </div>
          <span className="section-count">{researchBriefFixture.comparison.length} {t.showcase.brief.optionLabel}</span>
        </div>
        <div className="comparison-grid">
          {researchBriefFixture.comparison.map((row) => (
            <article className="comparison-option" key={row.option}>
              <h4>{row.option}</h4>
              <ComparisonField label={t.showcase.brief.integrationLabel} value={row.integration} />
              <ComparisonField label={t.showcase.brief.humanDecisionLabel} value={row.humanDecision} />
              <ComparisonField label={t.showcase.brief.evaluationLabel} value={row.evaluation} />
            </article>
          ))}
        </div>
      </section>

      <section className="findings-section" aria-labelledby="findings-heading">
        <div className="section-heading-row">
          <div>
            <p className="step-stage">{t.showcase.brief.evidenceLabel}</p>
            <h3 id="findings-heading">{t.showcase.brief.findingsLabel}</h3>
          </div>
          <span className="section-count">{researchBriefFixture.claims.length} {t.showcase.brief.claimLabel}</span>
        </div>
        <div className="claim-list">
          {researchBriefFixture.claims.map((claim, index) => (
            <article className="claim-item" id={`research-claim-${claim.claimId}`} key={claim.claimId} tabIndex={-1}>
              <div className="claim-number">{String(index + 1).padStart(2, "0")}</div>
              <div className="claim-body">
                <span>{t.showcase.brief.claimLabel}</span>
                <p>{claim.text}</p>
                <code>{t.showcase.brief.evidenceLabel}: {claim.evidenceId}</code>
              </div>
              <button
                className="claim-link"
                type="button"
                onClick={() => onSelectEvidence(claim.evidenceId, claim.claimId)}
              >
                {t.showcase.brief.inspectEvidence}
                <span aria-hidden="true">↗</span>
              </button>
            </article>
          ))}
        </div>
      </section>

      <p className="measurement-note">{t.showcase.brief.staticDisclosure}</p>
    </div>
  );
}

function ComparisonField({ label, value }: { label: string; value: string }) {
  return (
    <div className="comparison-field">
      <span>{label}</span>
      <p>{value}</p>
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
    <div className="blocked-showcase document-blocked-showcase">
      <article className="blocked-callout">
        <div className="blocked-callout-heading">
          <span className="blocked-icon" aria-hidden="true">!</span>
          <div>
            <p className="step-stage">{t.heading}</p>
            <h3>{t.reportUnavailable}</h3>
          </div>
        </div>
        <p>{t.summary}</p>
        <p>{t.detail}</p>
        <div className="blocked-status-row">
          <span>review_status</span>
          <strong>{t.review}</strong>
        </div>
        <div className="blocked-status-row">
          <span>delivery_status</span>
          <strong>{t.delivery}</strong>
        </div>
        <section className="next-clarification">
          <p className="step-stage">{copy[language].showcase.brief.nextClarification}</p>
          <h4>{copy[language].showcase.brief.nextClarificationDetail}</h4>
        </section>
      </article>

      <ResultReader language={language} mode="static" result={projection.result} />

      <details className="blocked-diagnostic-disclosure">
        <summary>{t.diagnostic}</summary>
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
      </details>
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

export function EvidenceSourceSidebar({
  language,
  projection,
  selection,
  onReturnToClaim,
  onSelectEvidence
}: {
  language: Language;
  projection: ConsoleProjection;
  selection: EvidenceSelection;
  onReturnToClaim: (claimId: string) => void;
  onSelectEvidence: (evidenceId: string) => void;
}) {
  return (
    <StaticEvidenceSourcePanel
      language={language}
      projection={projection}
      selection={selection}
      onReturnToClaim={onReturnToClaim}
      onSelectEvidence={onSelectEvidence}
    />
  );
}

export function LiveEvidenceSidebar({
  language,
  projection
}: {
  language: Language;
  projection: ConsoleProjection;
}) {
  return <LiveEvidenceSourcePanel language={language} projection={projection} />;
}
