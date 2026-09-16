import { useState } from "react";

import { copy, type Language, screenEnglishNames, screenKeys, type ScreenKey } from "../i18n";
import type { ShowcaseState } from "./showcaseWorkspace";

type StageKey = "question" | "work" | "evidence" | "review" | "delivery";

const stageKeys: StageKey[] = ["question", "work", "evidence", "review", "delivery"];

const stageScreens: Record<StageKey, ScreenKey> = {
  question: "command",
  work: "lifecycle",
  evidence: "evidence",
  review: "review",
  delivery: "result"
};

export function initialScreenForShowcase(showcaseState: ShowcaseState): ScreenKey {
  const initialStage: StageKey =
    showcaseState === "evidence" ? "evidence" : showcaseState === "blocked" ? "review" : "work";
  return stageScreens[initialStage];
}

export function StageRail({
  activeScreen,
  isLive,
  language,
  onSelectScreen
}: {
  activeScreen: ScreenKey;
  isLive: boolean;
  language: Language;
  onSelectScreen: (screen: ScreenKey) => void;
}) {
  const t = copy[language];
  const selectedStage = stageKeys.find((stage) => stageScreens[stage] === activeScreen) ?? "work";
  const [stageMenuOpen, setStageMenuOpen] = useState(defaultStageMenuOpen);

  return (
    <aside className="stage-rail left-rail">
      <details
        className="stage-rail-menu"
        open={stageMenuOpen}
        onToggle={(event) => setStageMenuOpen(event.currentTarget.open)}
      >
        <summary className="rail-heading">
          <span className="rail-marker">01</span>
          <span>
            <span className="rail-kicker">DRA / DELIVERY PATH</span>
            <span className="rail-title">{t.showcase.railLabel}</span>
          </span>
          <span className="rail-menu-toggle" aria-hidden="true" />
        </summary>
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
      </details>

      <details className="technical-disclosure technical-navigation" open={isLive}>
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
    </aside>
  );
}

function defaultStageMenuOpen(): boolean {
  return typeof window === "undefined" || window.innerWidth > 760;
}
