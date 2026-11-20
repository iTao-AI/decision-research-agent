import { useEffect, useId, useLayoutEffect, useRef, useState, type Ref } from "react";
import { copy, type Language } from "../i18n";
import type { BoundFinding, BoundSourceReference, ResearchFindingsReport, ResearchFindingsResponse } from "../researchFindings";
import { safeHttpUrl } from "./resultReader";

export type UnresolvedQuestionControls = {
  selectedQuestionIds: readonly string[];
  disabled: boolean;
  onToggleQuestion: (questionId: string) => void;
  onPrepare: () => void;
  prepareButtonRef: Ref<HTMLButtonElement>;
};

export function ResearchFindingsReader({ language, findings, followUp, variant }: {
  language: Language; findings: ResearchFindingsResponse; followUp?: UnresolvedQuestionControls;
  variant?: "workspace";
}) {
  const t = copy[language].research;
  const report = findings.report;
  const selection = followUp && <section className="research-follow-up-controls" aria-label={t.followUp.selectionTitle}>
    <h3>{t.followUp.selectionTitle}</h3><p>{t.followUp.selectionHint}</p>
    <button type="button" ref={followUp.prepareButtonRef} disabled={followUp.disabled || !followUp.selectedQuestionIds.length}
      onClick={followUp.onPrepare}>{t.followUp.prepare}</button>
  </section>;
  return (
    <article className={variant ? "research-findings-reader dw-findings-reader" : "research-findings-reader"} aria-label={t.title}>
      <h2>{t.title}</h2>
      {!variant && <p className="research-binding-boundary">{t.boundary}</p>}
      {!variant && selection}
      <QuestionReport key={`${report.run_id}/${report.profile_id}@${report.profile_version}/${findings.artifact.content_hash}`}
        language={language} report={report} followUp={followUp} variant={variant} />
      {variant && <p className="research-binding-boundary">{t.boundary}</p>}
      {variant && selection}
      <section aria-label={t.contradictions}>
        <h3>{t.contradictions}</h3><p>{t.contradictionsBoundary}</p>
        <TextEntries entries={report.reported_contradictions} empty={t.none} />
      </section>
      <section aria-label={t.limitations}>
        <h3>{t.limitations}</h3><TextEntries entries={report.limitations} empty={t.none} />
      </section>
    </article>
  );
}

function QuestionReport({ language, report, followUp, variant }: {
  language: Language; report: ResearchFindingsReport; followUp?: UnresolvedQuestionControls; variant?: "workspace";
}) {
  const t = copy[language].research;
  const id = useId();
  const [selectedQuestion, setSelectedQuestion] = useState<string>();
  const [selectedCitation, setSelectedCitation] = useState<number>();
  const citationTrigger = useRef<HTMLButtonElement>(null);
  const regions = useRef(new Map<string, HTMLElement>());
  const questions = report.questions.map((question, index) => ({
    ...question,
    regionId: `${id}-question-${index}`,
    disposition: report.dispositions.find((entry) => entry.question_id === question.question_id)!,
    findings: report.findings.filter((finding) => finding.question_id === question.question_id)
  }));
  const firstCitationNumbers = new Map<string, number>();
  if (variant) {
    let sourceNumber = 1;
    for (const finding of questions.flatMap((question) => question.findings)) {
      firstCitationNumbers.set(finding.finding_id, sourceNumber);
      sourceNumber += finding.references.length;
    }
  }
  const navigate = (questionId: string) => {
    setSelectedQuestion(questionId);
    const region = regions.current.get(questionId);
    region?.focus({ preventScroll: true });
    region?.scrollIntoView?.({ block: "start", behavior: "auto" });
  };
  const selectCitation = (number: number, trigger: HTMLButtonElement) => {
    citationTrigger.current = trigger;
    setSelectedCitation((current) => current === number ? undefined : number);
  };
  useLayoutEffect(() => {
    if (selectedCitation !== undefined) return;
    const trigger = citationTrigger.current;
    citationTrigger.current = null;
    trigger?.focus({ preventScroll: true });
    trigger?.scrollIntoView?.({ block: "center", behavior: "auto" });
  }, [selectedCitation]);
  const directory = (
    <nav aria-label={t.questionDirectory}>
        <ol className="research-question-list">
          {questions.map((question, index) => <li key={question.question_id}>
            <button type="button" aria-controls={question.regionId}
              aria-current={selectedQuestion === question.question_id ? "location" : undefined}
              onClick={() => navigate(question.question_id)}>
              <span className="research-question-number">{index + 1}</span>
              <span className="research-question-link-text">{question.text}</span>
              <small className={`research-question-disposition research-disposition-${question.disposition.status}`}>
                {question.disposition.status === "candidate_findings" ? t.candidateDisposition : t.unresolvedDisposition}
              </small>
            </button>
          </li>)}
        </ol>
      </nav>
  );
  return <div className="research-question-report">
    {variant ? <details className="dw-details dw-question-directory">
      <summary>{t.questionDirectory}</summary>
      {directory}
    </details> : <section aria-label={t.questions}>
      <h3>{t.questions}</h3>
      {directory}
    </section>}
    <section aria-label={t.byQuestion}>
      {!variant && <h3>{t.byQuestion}</h3>}
      {questions.map((question, index) => <section className="research-question-findings" key={question.question_id}
        id={question.regionId} aria-labelledby={`${question.regionId}-heading`} tabIndex={-1}
        ref={(element) => { if (element) regions.current.set(question.question_id, element); else regions.current.delete(question.question_id); }}>
        <div className="research-question-heading">
          <p className="research-question-order">{t.questionNumber(index + 1)}</p>
          <small className={`research-question-disposition research-disposition-${question.disposition.status}`}>
            {question.disposition.status === "candidate_findings" ? t.candidateDisposition : t.unresolvedDisposition}
          </small>
          <h4 id={`${question.regionId}-heading`}>{question.text}</h4>
        </div>
        {question.disposition.status === "unresolved" ? <>
          <p className="research-question-reason">{question.disposition.reason}</p>
          {followUp && <label className="research-unresolved-selection">
            <input type="checkbox" aria-label={t.followUp.selectQuestion(index + 1)} disabled={followUp.disabled}
              checked={followUp.selectedQuestionIds.includes(question.question_id)}
              onChange={() => followUp.onToggleQuestion(question.question_id)} />
            <span>{t.followUp.selectQuestion(index + 1)}</span>
          </label>}
        </> :
          question.findings.map((finding) => variant ? (
            <WorkspaceFinding key={finding.finding_id} language={language} finding={finding}
              firstCitation={firstCitationNumbers.get(finding.finding_id)!} selectedCitation={selectedCitation}
              onSelect={selectCitation} onReturn={() => setSelectedCitation(undefined)} />
          ) : (
            <article className="research-finding" key={finding.finding_id}>
              <p className="research-candidate-statement">{finding.statement}</p>
              {finding.references.map((reference, referenceIndex) => <SourceInspection
                key={referenceIndex} language={language} reference={reference} />)}
            </article>
          ))}
      </section>)}
    </section>
  </div>;
}

function WorkspaceFinding({ language, finding, firstCitation, selectedCitation, onSelect, onReturn }: {
  language: Language;
  finding: BoundFinding;
  firstCitation: number;
  selectedCitation?: number;
  onSelect: (number: number, trigger: HTMLButtonElement) => void;
  onReturn: () => void;
}) {
  const id = useId();
  const activeReference = selectedCitation === undefined ? undefined : finding.references[selectedCitation - firstCitation];
  return <article className={activeReference ? "research-finding dw-finding-has-source" : "research-finding"}>
    <div className="dw-finding-reading">
      <p className="research-candidate-statement">
        {finding.statement}
        {finding.references.map((_, index) => {
          const number = firstCitation + index;
          return <button key={number} className="dw-reference" type="button"
            aria-label={language === "zh" ? `查看来源 ${number}` : `View source ${number}`}
            aria-expanded={number === selectedCitation} aria-controls={`${id}-source-${number}`}
            onClick={(event) => onSelect(number, event.currentTarget)}>{number}</button>;
        })}
      </p>
    </div>
    {activeReference && <SourceInspection key={selectedCitation} language={language} reference={activeReference}
      workspace={{ id: `${id}-source-${selectedCitation}`, number: selectedCitation!, onReturn }} />}
  </article>;
}

function TextEntries({ entries, empty }: { entries: readonly string[]; empty: string }) {
  return entries.length ? <ul>{entries.map((entry, index) => <li key={index}>{entry}</li>)}</ul> : <p>{empty}</p>;
}

function SourceInspection({ language, reference, workspace }: {
  language: Language; reference: BoundSourceReference;
  workspace?: { id: string; number: number; onReturn: () => void };
}) {
  const t = copy[language].research;
  const [open, setOpen] = useState(false);
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const snippetRegion = useRef<HTMLDivElement>(null);
  const sourceRegion = useRef<HTMLElement>(null);
  const sourceId = workspace?.id;
  const href = safeHttpUrl(reference.source_url);
  useEffect(() => {
    if (!sourceId) return;
    sourceRegion.current?.focus({ preventScroll: true });
    sourceRegion.current?.scrollIntoView?.({ block: "nearest", behavior: "auto" });
  }, [sourceId]);
  useEffect(() => {
    if (open) {
      snippetRegion.current?.focus();
      snippetRegion.current?.scrollIntoView?.({ block: "nearest", behavior: "auto" });
    }
  }, [open]);
  const Container = workspace ? "aside" : "section";
  const title = workspace ? `${t.source} ${workspace.number}` : t.source;
  const SnippetHeading = workspace ? "h6" : "h5";
  return <Container className={workspace ? "research-source-inspection dw-source-panel" : "research-source-inspection"}
    aria-label={title} id={sourceId} tabIndex={workspace ? -1 : undefined} ref={sourceRegion}
    onKeyDown={workspace ? (event) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        workspace.onReturn();
      }
    } : undefined}>
    {workspace && <h5 className="dw-source-heading">{title}</h5>}
    <p className="research-source-url">
      {href ? <a href={href} target="_blank" rel="noopener noreferrer">{reference.source_url}</a> : <span>{reference.source_url}</span>}
    </p>
    {!href && <p>{t.unsafeLink}</p>}
    <strong>{t.excerpt}</strong>
    <blockquote>{reference.excerpt}</blockquote>
    <button aria-expanded={open} aria-controls={id} ref={trigger} type="button" onClick={() => setOpen((current) => !current)}>{t.inspect}</button>
    {open && <div className="research-full-snippet" role="region" aria-label={t.fullSnippet} id={id} ref={snippetRegion} tabIndex={-1}>
      <SnippetHeading>{t.fullSnippet}</SnippetHeading><p>{t.snippetBoundary}</p>
      <pre>{reference.snippet}</pre>
      <button type="button" onClick={() => { setOpen(false); trigger.current?.focus(); }}>{t.returnToExcerpt}</button>
    </div>}
    <details className="research-binding-technical">
      <summary>{t.technical}</summary>
      <dl>
        <dt>evidence_id</dt><dd>{reference.evidence_id}</dd>
        <dt>source_identity</dt><dd>{reference.source_identity}</dd>
        <dt>evidence_fingerprint</dt><dd>{reference.evidence_fingerprint}</dd>
        <dt>excerpt_start / excerpt_end (Unicode code points)</dt><dd>{reference.excerpt_start} / {reference.excerpt_end}</dd>
      </dl>
    </details>
    {workspace && <button className="dw-return-citation" type="button" onClick={workspace.onReturn}>
      {language === "zh" ? "返回引用处" : "Return to citation"}
    </button>}
  </Container>;
}
