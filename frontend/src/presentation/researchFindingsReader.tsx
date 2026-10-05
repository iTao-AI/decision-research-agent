import { useEffect, useId, useRef, useState } from "react";
import { copy, type Language } from "../i18n";
import type { BoundSourceReference, ResearchFindingsResponse } from "../researchFindings";
import { safeHttpUrl } from "./resultReader";

export function ResearchFindingsReader({ language, findings }: { language: Language; findings: ResearchFindingsResponse }) {
  const t = copy[language].research;
  const report = findings.report;
  return (
    <article className="research-findings-reader" aria-label={t.title}>
      <h2>{t.title}</h2>
      <p className="research-binding-boundary">{t.boundary}</p>
      <section aria-label={t.questions}>
        <h3>{t.questions}</h3>
        <ol className="research-question-list">
          {report.questions.map((question) => <li key={question.question_id}>
            <span>{question.text}</span>{" "}
            <small className="research-question-disposition">{report.dispositions.find((d) => d.question_id === question.question_id)?.status === "candidate_findings"
              ? t.candidateDisposition : t.unresolvedDisposition}</small>
          </li>)}
        </ol>
      </section>
      <section aria-label={t.findings}>
        <h3>{t.findings}</h3>
        {report.questions.map((question) => {
          const related = report.findings.filter((finding) => finding.question_id === question.question_id);
          return related.length > 0 && <section className="research-question-findings" key={question.question_id}>
            <h4>{question.text}</h4>
            {related.map((finding) => <article className="research-finding" key={finding.finding_id}>
              <p className="research-candidate-statement">{finding.statement}</p>
              {finding.references.map((reference, index) => <SourceInspection
                key={`${finding.finding_id}-${index}`} language={language} reference={reference} />)}
            </article>)}
          </section>;
        })}
      </section>
      <section aria-label={t.unresolved}>
        <h3>{t.unresolved}</h3>
        {report.dispositions.some((d) => d.status === "unresolved") ? <ul>
          {report.dispositions.filter((d) => d.status === "unresolved").map((disposition) => <li key={disposition.question_id}>
            <strong>{report.questions.find((q) => q.question_id === disposition.question_id)?.text}</strong>
            <p>{disposition.reason}</p>
          </li>)}
        </ul> : <p>{t.none}</p>}
      </section>
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
