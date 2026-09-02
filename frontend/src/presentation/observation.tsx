import { type ReactNode } from "react";

import { type Observation } from "../consoleProjection";
import { copy, type Language, type ScreenKey } from "../i18n";

export function ObservationSection<T>({
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

export function ObservationValue<T>({
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

export function observationLabel<T>(observation: Observation<T>, language: Language): string {
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

export function KeyValueList({ entries }: { entries: Array<[string, ReactNode]> }) {
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

export function countSummary(counts: Readonly<Record<string, number>>) {
  const entries = Object.entries(counts);
  return entries.length === 0
    ? "{}"
    : entries.map(([key, value]) => `${key}: ${value}`).join(", ");
}

export function buildScreenSummary(screen: ScreenKey) {
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
