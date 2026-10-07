import { useEffect, useId, useRef, useState, type Ref } from "react";
import { copy, type Language } from "../i18n";
import type { BoundSourceReference, ResearchFindingsReport, ResearchFindingsResponse } from "../researchFindings";
import { safeHttpUrl } from "./resultReader";

type UnresolvedQuestionControls = {
  selectedQuestionIds: readonly string[];
  disabled: boolean;
  onToggleQuestion: (questionId: string) => void;
  onPrepare: () => void;
  prepareButtonRef: Ref<HTMLButtonElement>;
};

export function ResearchFindingsReader({ language, findings, followUp }: {
  language: Language; findings: ResearchFindingsResponse; followUp?: UnresolvedQuestionControls;
}) {
  const t = copy[language].research;
  const report = findings.report;
  return (
    <article className="research-findings-reader" aria-label={t.title}>
      <h2>{t.title}</h2>
      <p className="research-binding-boundary">{t.boundary}</p>
      {followUp && <section className="research-follow-up-controls" aria-label={t.followUp.selectionTitle}>
        <h3>{t.followUp.selectionTitle}</h3><p>{t.followUp.selectionHint}</p>
        <button type="button" ref={followUp.prepareButtonRef} disabled={followUp.disabled || !followUp.selectedQuestionIds.length}
          onClick={followUp.onPrepare}>{t.followUp.prepare}</button>
      </section>}
      <QuestionReport key={`${report.run_id}/${report.profile_id}@${report.profile_version}`} language={language} report={report} followUp={followUp} />
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

function QuestionReport({ language, report, followUp }: { language: Language; report: ResearchFindingsReport; followUp?: UnresolvedQuestionControls }) {
  const t = copy[language].research;
  const id = useId();
  const [selectedQuestion, setSelectedQuestion] = useState<string>();
  const regions = useRef(new Map<string, HTMLElement>());
  const questions = report.questions.map((question, index) => ({
    ...question,
    regionId: `${id}-question-${index}`,
    disposition: report.dispositions.find((entry) => entry.question_id === question.question_id)!,
    findings: report.findings.filter((finding) => finding.question_id === question.question_id)
  }));
  const navigate = (questionId: string) => {
    setSelectedQuestion(questionId);
    const region = regions.current.get(questionId);
    region?.focus({ preventScroll: true });
    region?.scrollIntoView?.({ block: "start", behavior: "auto" });
  };
  return <div className="research-question-report">
    <section aria-label={t.questions}>
      <h3>{t.questions}</h3>
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
    </section>
    <section aria-label={t.byQuestion}>
      <h3>{t.byQuestion}</h3>
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
          question.findings.map((finding) => <article className="research-finding" key={finding.finding_id}>
            <p className="research-candidate-statement">{finding.statement}</p>
            {finding.references.map((reference, referenceIndex) => <SourceInspection
              key={`${finding.finding_id}-${referenceIndex}`} language={language} reference={reference} />)}
          </article>)}
      </section>)}
    </section>
  </div>;
}

function TextEntries({ entries, empty }: { entries: readonly string[]; empty: string }) {
  return entries.length ? <ul>{entries.map((entry, index) => <li key={index}>{entry}</li>)}</ul> : <p>{empty}</p>;
}

function SourceInspection({ language, reference }: { language: Language; reference: BoundSourceReference }) {
  const t = copy[language].research;
  const [open, setOpen] = useState(false);
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const snippetRegion = useRef<HTMLDivElement>(null);
  const href = safeHttpUrl(reference.source_url);
  useEffect(() => {
    if (open) {
      snippetRegion.current?.focus();
      snippetRegion.current?.scrollIntoView?.({ block: "nearest", behavior: "auto" });
    }
  }, [open]);
  return <section className="research-source-inspection" aria-label={t.source}>
    <p className="research-source-url">
      {href ? <a href={href} target="_blank" rel="noopener noreferrer">{reference.source_url}</a> : <span>{reference.source_url}</span>}
    </p>
    {!href && <p>{t.unsafeLink}</p>}
    <strong>{t.excerpt}</strong>
    <blockquote>{reference.excerpt}</blockquote>
    <button aria-expanded={open} aria-controls={id} ref={trigger} type="button" onClick={() => setOpen((current) => !current)}>{t.inspect}</button>
    {open && <div className="research-full-snippet" role="region" aria-label={t.fullSnippet} id={id} ref={snippetRegion} tabIndex={-1}>
      <h5>{t.fullSnippet}</h5><p>{t.snippetBoundary}</p>
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
  </section>;
}
