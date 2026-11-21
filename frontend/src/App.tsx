import { useEffect, useMemo, useState } from "react";

import { buildStaticConsoleProjection } from "./consoleProjection";
import { researchBriefFixture } from "./demoData";
import { copy, type Language, screenEnglishNames, type ScreenKey } from "./i18n";
import { JudgmentSidebar } from "./presentation/judgmentSidebar";
import { initialScreenForShowcase, TechnicalScreenNavigation } from "./presentation/stageRail";
import { type ShowcaseState } from "./presentation/showcaseWorkspace";
import { StaticReportSurface } from "./presentation/staticReportSurface";
import type { EvidenceSelection } from "./presentation/evidenceSourcePanel";
import {
  ArchitectureMode,
  CanonicalResult,
  CommandCenter,
  EvidenceLedger,
  Metric,
  ReviewVerification,
  RunLifecycle
} from "./presentation/technicalScreens";
import { buildScreenSummary, observationLabel } from "./presentation/observation";
import { ResearchWorkspace } from "./ResearchWorkspace";
import type { LiveRunOptions } from "./useLiveRun";

export type { ShowcaseState } from "./presentation/showcaseWorkspace";

export default function App({ liveOptions, showcaseState }: {
  liveOptions?: LiveRunOptions;
  showcaseState?: ShowcaseState;
}) {
  const scenario = showcaseState ?? readShowcaseRoute();
  return scenario
    ? <ShowcaseConsole key={scenario} scenario={scenario} />
    : <ResearchWorkspace liveOptions={liveOptions} />;
}

function readShowcaseRoute(): ShowcaseState | undefined {
  if (typeof window === "undefined") return undefined;
  const value = new URLSearchParams(window.location.search).get("showcase");
  if (value === "evidence" || value === "blocked" || value === "overview") return value;
  return undefined;
}

function ShowcaseConsole({ scenario }: { scenario: ShowcaseState }) {
  const [language, setLanguage] = useState<Language>("zh");
  const [activeScreen, setActiveScreen] = useState<ScreenKey>(() => initialScreenForShowcase(scenario));
  const projection = useMemo(() => buildStaticConsoleProjection(scenario === "blocked" ? "blocked" : "normal"), [scenario]);
  const t = copy[language];
  const [selection, setSelection] = useState<EvidenceSelection>(() => {
    const claim = scenario === "evidence" ? researchBriefFixture.claims[1] : undefined;
    return {
      evidenceId: claim?.evidenceId ?? researchBriefFixture.sources[scenario === "blocked" ? 1 : 0].evidenceId,
      ...(claim ? { claimId: claim.claimId } : {}),
      focus: "none",
      navigationRequestId: 0
    };
  });
  const returnToClaim = (claimId: string) => setSelection((current) => ({
    ...current, claimId, focus: "claim", navigationRequestId: current.navigationRequestId + 1
  }));
  const selectEvidence = (evidenceId: string, claimId?: string) => setSelection((current) => ({
    evidenceId, ...(claimId ? { claimId } : {}), focus: "detail", navigationRequestId: current.navigationRequestId + 1
  }));

  useEffect(() => {
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  }, [language]);

  return (
    <div className={`console-shell showcase-${scenario} showcase-route`}>
      <header className="top-bar">
        <div className="brand-block">
          <h1>{t.showcase.headerTitle}</h1>
          <p className="subtitle">{t.showcase.headerDescription}</p>
        </div>
        <div className="top-actions" aria-label={t.language}>
          <span>{t.language}</span>
          <button className={language === "zh" ? "active" : ""} aria-pressed={language === "zh"}
            type="button" onClick={() => setLanguage("zh")}>{t.chinese}</button>
          <button className={language === "en" ? "active" : ""} aria-pressed={language === "en"}
            type="button" onClick={() => setLanguage("en")}>{t.english}</button>
          <a href="/">{language === "zh" ? "研究工作台" : "Research workspace"}</a>
        </div>
      </header>
      <div className="workspace static-workspace">
        <main className="canvas static-mode">
          <StaticReportSurface language={language} projection={projection} showcaseState={scenario}
            selection={selection} onReturnToClaim={returnToClaim} onSelectEvidence={selectEvidence} />
          <details className="technical-disclosure technical-console-view">
            <summary>
              <span>{t.showcase.technicalLabel}</span>
              <small>{t.showcase.technicalDescription}</small>
            </summary>
            <TechnicalScreenNavigation activeScreen={activeScreen} className="static-technical-navigation"
              language={language} onSelectScreen={setActiveScreen} />
            <section className="status-grid" aria-label="Run state summary">
              <Metric label={t.labels.service} value={observationLabel(projection.summary.service, language)} tone="blue" />
              <Metric label={t.labels.health} value={observationLabel(projection.summary.health, language)} tone="amber" />
              <Metric label={t.labels.mode} value={projection.summary.mode} tone="cyan" />
              <Metric label={t.labels.run} value={observationLabel(projection.summary.runId, language)} tone="green" />
            </section>
            <section className="primary-panel">
              <div className="panel-heading">
                <div>
                  <p className="kicker">{screenEnglishNames[activeScreen]}</p>
                  <h2>{screenEnglishNames[activeScreen]}</h2>
                </div>
                <span className="status-pill">{buildScreenSummary(activeScreen)}</span>
              </div>
              <p className="statement">{t.statements[activeScreen]}</p>
              {activeScreen === "command" && <CommandCenter language={language} projection={projection} />}
              {activeScreen === "lifecycle" && <RunLifecycle language={language} projection={projection} />}
              {activeScreen === "evidence" && <EvidenceLedger language={language} projection={projection} />}
              {activeScreen === "review" && <ReviewVerification language={language} projection={projection} />}
              {activeScreen === "result" && <CanonicalResult language={language} projection={projection} />}
              {activeScreen === "architecture" && <ArchitectureMode language={language} projection={projection} />}
            </section>
          </details>
        </main>
        <JudgmentSidebar isShowcaseRoute language={language} projection={projection} showcaseState={scenario}
          selection={selection} onReturnToClaim={returnToClaim} onSelectEvidence={selectEvidence} />
      </div>
    </div>
  );
}
