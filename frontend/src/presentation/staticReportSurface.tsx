import { type ConsoleProjection } from "../consoleProjection";
import { copy, type Language } from "../i18n";
import type { EvidenceSelection } from "./evidenceSourcePanel";
import { ShowcaseWorkspace, type ShowcaseState } from "./showcaseWorkspace";

export function StaticReportSurface({
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
  const t = copy[language];
  return (
    <section className="research-work-surface">
      <div className="surface-heading">
        <div className="question-block">
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
      <p className="case-disclosure">{t.showcase.brief.staticDisclosure}</p>
      {showcaseState !== "blocked" && <ReportShortcuts language={language} />}
      <ShowcaseWorkspace
        language={language}
        projection={projection}
        showcaseState={showcaseState}
        selection={selection}
        onReturnToClaim={onReturnToClaim}
        onSelectEvidence={onSelectEvidence}
      />
    </section>
  );
}

function ReportShortcuts({ language }: { language: Language }) {
  const t = copy[language];
  return (
    <nav aria-label={t.showcase.quickNavigationLabel} className="report-shortcuts">
      <button type="button" onClick={() => focusAndScrollTo("conclusion-section")}>
        {t.showcase.conclusionLink}
      </button>
      <button type="button" onClick={() => focusAndScrollTo("evidence-detail")}>
        {t.showcase.evidenceLink}
      </button>
      <button
        type="button"
        onClick={() => {
          const disclosure = document.getElementById("full-report-disclosure");
          if (disclosure instanceof HTMLDetailsElement) {
            disclosure.open = true;
          }
          focusAndScrollTo("full-report-content");
        }}
      >
        {t.showcase.reportLink}
      </button>
    </nav>
  );
}

function focusAndScrollTo(targetId: string) {
  const target = document.getElementById(targetId);
  if (!target) {
    return;
  }
  target.focus();
  target.scrollIntoView?.({ block: "start" });
}
