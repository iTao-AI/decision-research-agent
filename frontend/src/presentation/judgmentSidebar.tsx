import {
  type ConsoleProjection,
  type Observation
} from "../consoleProjection";
import { copy, type Language } from "../i18n";
import { observationLabel } from "./observation";
import {
  EvidenceSourceSidebar,
  LiveEvidenceSidebar,
  type ShowcaseState
} from "./showcaseWorkspace";
import type { EvidenceSelection } from "./evidenceSourcePanel";

const authorityBadges = [
  "Application DB",
  "LangGraph checkpoint",
  "LangSmith diagnostics",
  "GET /api/runs/{run_id}/result"
];

export function JudgmentSidebar({
  isShowcaseRoute,
  language,
  projection,
  showcaseState,
  selection,
  onReturnToClaim,
  onSelectEvidence
}: {
  isShowcaseRoute: boolean;
  language: Language;
  projection: ConsoleProjection;
  showcaseState: ShowcaseState;
  selection: EvidenceSelection;
  onReturnToClaim: (claimId: string) => void;
  onSelectEvidence: (evidenceId: string) => void;
}) {
  const t = copy[language];
  const blocked = showcaseState === "blocked";
  const reviewStatus =
    projection.review.status.kind === "observed" ? projection.review.status.value : "not_observed";

  return (
    <aside className="inspector judgment-sidebar">
      <EvidenceSourceSidebar
        language={language}
        projection={projection}
        selection={selection}
        onReturnToClaim={onReturnToClaim}
        onSelectEvidence={onSelectEvidence}
      />
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

      <details className="technical-disclosure inspector-technical">
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

export function LiveJudgmentSidebar({
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
      <LiveEvidenceSidebar language={language} projection={projection} />
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
