import { useEffect, useRef, useState } from "react";

import { researchBriefFixture } from "../demoData";
import { type ConsoleProjection, type EvidenceView } from "../consoleProjection";
import { copy, type Language } from "../i18n";
import { KeyValueList, ObservationValue } from "./observation";
import { safeHttpUrl } from "./resultReader";

export type EvidenceSelection = Readonly<{
  evidenceId: string;
  claimId?: string;
  focus: "none" | "detail" | "claim";
}>;

export function StaticEvidenceSourcePanel({
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
  const t = copy[language];
  const detailRef = useRef<HTMLElement>(null);
  const evidence = projection.evidence.kind === "observed" ? projection.evidence.value : [];
  const selectedEvidence = findEvidence(evidence, selection.evidenceId);
  const selectedFixture = researchBriefFixture.sources.find(
    (source) => source.evidenceId === selection.evidenceId
  );
  const selectedClaim = researchBriefFixture.claims.find(
    (claim) => claim.claimId === selection.claimId && claim.evidenceId === selection.evidenceId
  );

  useEffect(() => {
    if (selection.focus === "detail") {
      detailRef.current?.focus();
    }
  }, [selection.evidenceId, selection.focus]);

  if (projection.evidence.kind !== "observed") {
    return (
      <section className="source-panel" aria-label={t.showcase.brief.sourceListLabel}>
        <SourcePanelHeading language={language} />
        <ObservationValue language={language} observation={projection.evidence} />
      </section>
    );
  }

  return (
    <section className="source-panel" aria-label={t.showcase.brief.sourceListLabel}>
      <SourcePanelHeading language={language} />
      <ul className="source-list">
        {researchBriefFixture.sources.map((source) => {
          const entry = findEvidence(evidence, source.evidenceId);
          const isSelected = source.evidenceId === selection.evidenceId;
          return (
            <li key={source.evidenceId}>
              <button
                aria-pressed={isSelected}
                className={isSelected ? "source-item active" : "source-item"}
                type="button"
                onClick={() => onSelectEvidence(source.evidenceId)}
              >
                <span>{source.title}</span>
                <small>
                  {source.evidenceId} · {sourceStatusLabel(entry, t.showcase.brief)}
                </small>
              </button>
            </li>
          );
        })}
      </ul>
      <article
        aria-label={t.showcase.brief.sourceDetailLabel}
        className="source-detail"
        id="evidence-detail"
        ref={detailRef}
        tabIndex={-1}
      >
        <div className="source-detail-heading">
          <div>
            <p className="sidebar-kicker">{t.showcase.brief.sourceDetailLabel}</p>
            <h3>{selectedFixture?.title ?? selection.evidenceId}</h3>
          </div>
          <span className={selectedEvidence?.sourceStatus === "unconfirmed" ? "source-status blocked" : "source-status"}>
            {sourceStatusLabel(selectedEvidence, t.showcase.brief)}
          </span>
        </div>
        {selectedEvidence?.sourceStatus === "unconfirmed" ? (
          <p className="source-warning">{t.showcase.brief.claimsUnavailable}</p>
        ) : selectedClaim ? (
          <div className="source-claim">
            <span>{t.showcase.brief.claimLabel}</span>
            <p>{selectedClaim.text}</p>
          </div>
        ) : (
          <p className="source-warning">{t.showcase.brief.noClaim}</p>
        )}
        {selectedClaim && selectedEvidence?.sourceStatus !== "unconfirmed" && (
          <figure className="source-excerpt">
            <figcaption>{t.showcase.brief.excerptLabel}</figcaption>
            <blockquote>{selectedClaim.excerpt}</blockquote>
          </figure>
        )}
        {selectedFixture && (
          <div className="source-document">
            <span>{t.showcase.brief.sourceTextLabel}</span>
            <p>{selectedFixture.content}</p>
          </div>
        )}
        {selectedEvidence && <LiveLikeSourceMetadata language={language} entry={selectedEvidence} />}
        {selection.claimId && selectedClaim && (
          <button className="return-to-claim" type="button" onClick={() => onReturnToClaim(selection.claimId!)}>
            {t.showcase.brief.returnToClaim}
          </button>
        )}
      </article>
    </section>
  );
}

export function LiveEvidenceSourcePanel({
  language,
  projection
}: {
  language: Language;
  projection: ConsoleProjection;
}) {
  const t = copy[language];
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string>();
  const detailRef = useRef<HTMLElement>(null);
  const evidence = projection.evidence.kind === "observed" ? projection.evidence.value : [];
  const selectedId = selectedEvidenceId ?? evidence[0]?.evidenceId;
  const selectedEvidence = evidence.find((entry) => entry.evidenceId === selectedId);

  useEffect(() => {
    if (selectedEvidenceId) {
      detailRef.current?.focus();
    }
  }, [selectedEvidenceId]);

  if (projection.evidence.kind !== "observed") {
    return (
      <section className="source-panel" aria-label={t.showcase.brief.sourceListLabel}>
        <SourcePanelHeading language={language} />
        <ObservationValue language={language} observation={projection.evidence} />
      </section>
    );
  }

  if (evidence.length === 0) {
    return (
      <section className="source-panel" aria-label={t.showcase.brief.sourceListLabel}>
        <SourcePanelHeading language={language} />
        <p className="observation observed-empty">{t.observations.observedEmptyEvidence}</p>
      </section>
    );
  }

  return (
    <section className="source-panel" aria-label={t.showcase.brief.sourceListLabel}>
      <SourcePanelHeading language={language} />
      <ul className="source-list">
        {evidence.map((entry) => (
          <li key={entry.evidenceId}>
            <button
              aria-pressed={entry.evidenceId === selectedId}
              className={entry.evidenceId === selectedId ? "source-item active" : "source-item"}
              type="button"
              onClick={() => setSelectedEvidenceId(entry.evidenceId)}
            >
              <span>{entry.sourceIdentity}</span>
              <small>{entry.evidenceId} · {entry.verificationStatus}</small>
            </button>
          </li>
        ))}
      </ul>
      {selectedEvidence && (
        <article
          aria-label={t.showcase.brief.sourceDetailLabel}
          className="source-detail"
          ref={detailRef}
          tabIndex={-1}
        >
          <div className="source-detail-heading">
            <div>
              <p className="sidebar-kicker">{t.showcase.brief.sourceDetailLabel}</p>
              <h3>{selectedEvidence.sourceIdentity}</h3>
            </div>
            <span className="source-status">{selectedEvidence.verificationStatus}</span>
          </div>
          <p className="source-warning">{t.showcase.brief.noExcerpt}</p>
          <p className="source-field">
            <span>{t.labels.evidence}</span>
            <strong>{selectedEvidence.evidenceId}</strong>
          </p>
          <p className="source-field">
            <span>{t.showcase.brief.sourceUrl}</span>
            <SafeSourceLink language={language} evidence={selectedEvidence} />
          </p>
          <LiveLikeSourceMetadata language={language} entry={selectedEvidence} />
        </article>
      )}
    </section>
  );
}

function SourcePanelHeading({ language }: { language: Language }) {
  const t = copy[language];
  return (
    <div className="source-panel-heading">
      <div>
        <p className="sidebar-kicker">{t.showcase.brief.sourceListLabel}</p>
        <p>{t.showcase.brief.sourceListDetail}</p>
      </div>
      <span className="source-count">{t.labels.evidence}</span>
    </div>
  );
}

function LiveLikeSourceMetadata({ language, entry }: { language: Language; entry: EvidenceView }) {
  const t = copy[language];
  return (
    <details className="source-technical">
      <summary>{t.reader.technicalDetails}</summary>
      <KeyValueList
        entries={[
          ["evidence_id", entry.evidenceId],
          ["fingerprint", entry.fingerprint],
          ["citation_status", <ObservationValue language={language} observation={entry.citationStatus} />],
          ["verification_status", entry.verificationStatus],
          ["citedBy", <ObservationValue language={language} observation={entry.citedBy} />]
        ]}
      />
    </details>
  );
}

function SafeSourceLink({ language, evidence }: { language: Language; evidence: EvidenceView }) {
  const t = copy[language];
  if (evidence.sourceUrl.kind !== "observed") {
    return <ObservationValue language={language} observation={evidence.sourceUrl} />;
  }
  const safeUrl = safeHttpUrl(evidence.sourceUrl.value);
  if (!safeUrl) {
    return <span className="source-url-blocked">{t.showcase.brief.sourceUrlBlocked}</span>;
  }
  return (
    <a href={safeUrl} rel="noreferrer" target="_blank">
      {evidence.sourceUrl.value}
    </a>
  );
}

function findEvidence(evidence: readonly EvidenceView[], evidenceId: string): EvidenceView | undefined {
  return evidence.find((entry) => entry.evidenceId === evidenceId) ?? evidence[0];
}

function sourceStatusLabel(
  entry: EvidenceView | undefined,
  t: { sourceObserved: string; sourceUnconfirmed: string }
): string {
  return entry?.sourceStatus === "unconfirmed"
    ? t.sourceUnconfirmed
    : t.sourceObserved;
}
