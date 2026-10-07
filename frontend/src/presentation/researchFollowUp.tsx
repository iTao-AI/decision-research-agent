import { useEffect, useRef, useState } from "react";
import { validateLiveDemoQuery } from "../apiClient";
import { copy, type Language } from "../i18n";
import type { ResearchFindingsResponse, ResearchQuestion } from "../researchFindings";
import { RESEARCH_QUESTIONS_MAX, validateResearchQuestions } from "../researchScope";
import { ResearchFindingsReader } from "./researchFindingsReader";
import { ResearchScopeEditor } from "./researchScopeEditor";

type PreparedDraft = {
  questions: readonly ResearchQuestion[];
  references: readonly { questionId: string; text: string; reason: string }[];
  revision: number;
};

/** Browser-local input preparation. Accepted report and creation authority stay on the service. */
export function ResearchFollowUp({ language, findings, disabled, onStart }: {
  language: Language;
  findings: ResearchFindingsResponse;
  disabled: boolean;
  onStart: (questions: readonly ResearchQuestion[]) => Promise<void>;
}) {
  const t = copy[language].research;
  const [selected, setSelected] = useState<readonly string[]>([]);
  const [draft, setDraft] = useState<PreparedDraft>();
  const [replacePending, setReplacePending] = useState(false);
  const nextQuestionId = useRef(1);
  const revision = useRef(0);
  const submitting = useRef(false);
  const draftRegion = useRef<HTMLElement>(null);
  const prepareButton = useRef<HTMLButtonElement>(null);
  const replaceButton = useRef<HTMLButtonElement>(null);
  const unresolved = findings.report.questions.flatMap((question) => {
    const disposition = findings.report.dispositions.find((entry) => entry.question_id === question.question_id);
    return disposition?.status === "unresolved"
      ? [{ questionId: question.question_id, text: question.text, reason: disposition.reason! }] : [];
  });
  const selectedReferences = unresolved.filter((question) => selected.includes(question.questionId));
  const scopeValid = draft && validateResearchQuestions(draft.questions).ok
    && validateLiveDemoQuery(draft.questions[0].text).ok;

  useEffect(() => {
    if (draft?.revision) {
      draftRegion.current?.querySelector<HTMLTextAreaElement>("textarea")?.focus();
      draftRegion.current?.scrollIntoView?.({ block: "start", behavior: "auto" });
    }
  }, [draft?.revision]);
  useEffect(() => {
    if (replacePending) replaceButton.current?.focus();
  }, [replacePending]);

  const replaceDraft = () => {
    if (disabled || !selectedReferences.length) return;
    nextQuestionId.current = selectedReferences.length + 1;
    setDraft({
      questions: selectedReferences.map((question, index) => ({ question_id: `q${index + 1}`, text: question.text })),
      references: selectedReferences,
      revision: ++revision.current
    });
    setReplacePending(false);
  };
  const prepare = () => {
    if (disabled || !selectedReferences.length) return;
    if (draft) setReplacePending(true);
    else replaceDraft();
  };
  const start = async () => {
    if (!draft || disabled || replacePending || !scopeValid || submitting.current) return;
    submitting.current = true;
    try { await onStart(draft.questions); }
    finally { submitting.current = false; }
  };
  const editQuestions = (update: (questions: readonly ResearchQuestion[]) => readonly ResearchQuestion[]) => {
    if (disabled || replacePending) return;
    setDraft((current) => current ? { ...current, questions: update(current.questions) } : current);
  };

  return <>
    <ResearchFindingsReader language={language} findings={findings} followUp={unresolved.length ? {
      selectedQuestionIds: selected,
      disabled,
      onToggleQuestion: (questionId) => {
        if (!disabled) setSelected((current) => current.includes(questionId)
          ? current.filter((id) => id !== questionId) : [...current, questionId]);
      },
      onPrepare: prepare,
      prepareButtonRef: prepareButton
    } : undefined} />
    {draft && <section className="research-follow-up" role="region" aria-label={t.followUp.title} ref={draftRegion}>
      <h2>{t.followUp.title}</h2>
      <p>{t.followUp.boundary}</p>
      <p>{t.followUp.profile}: <strong>{t.structuredMode}</strong></p>
      <details className="research-draft-reference" open>
        <summary>{t.followUp.reference}</summary>
        <p>{t.followUp.sourceRun}: <code>{findings.run_id}</code></p>
        <ul>{draft.references.map((reference) => <li key={reference.questionId}>
          <strong>{reference.text}</strong><p>{reference.reason}</p>
        </li>)}</ul>
      </details>
      {replacePending && <div className="research-draft-replacement" role="alert">
        <p>{t.followUp.replaceWarning}</p>
        <div className="research-draft-actions">
          <button type="button" ref={replaceButton} disabled={disabled || !selectedReferences.length} onClick={replaceDraft}>{t.followUp.replace}</button>
          <button type="button" disabled={disabled} onClick={() => setReplacePending(false)}>{t.followUp.keep}</button>
        </div>
      </div>}
      <ResearchScopeEditor language={language} questions={draft.questions} disabled={disabled || replacePending}
        idPrefix="new-research-scope" legend={t.followUp.title} questionLabel={t.followUp.question}
        onEdit={(questionId, text) => editQuestions((questions) => questions.map((question) =>
          question.question_id === questionId ? { ...question, text } : question))}
        onRemove={(questionId) => editQuestions((questions) => questions.length > 1
          ? questions.filter((question) => question.question_id !== questionId) : questions)}
        onAdd={() => {
          if (disabled || replacePending || draft.questions.length >= RESEARCH_QUESTIONS_MAX) return;
          const question_id = `q${nextQuestionId.current++}`;
          editQuestions((questions) => [...questions, { question_id, text: "" }]);
        }} />
      <div className="research-draft-actions">
        <button type="button" disabled={disabled || replacePending || !scopeValid} onClick={start}>{t.followUp.confirm}</button>
        <button type="button" disabled={disabled} onClick={() => {
          setDraft(undefined); setReplacePending(false); prepareButton.current?.focus();
        }}>{t.followUp.cancel}</button>
      </div>
    </section>}
  </>;
}
