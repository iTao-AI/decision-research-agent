import { useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { validateLiveDemoQuery } from "../apiClient";
import { copy, type Language } from "../i18n";
import { STRUCTURED_RESEARCH_PROFILE, type ResearchFindingsResponse, type ResearchQuestion } from "../researchFindings";
import { RESEARCH_QUESTIONS_MAX, validateResearchQuestions } from "../researchScope";
import type { useLiveRun } from "../useLiveRun";
import { ResearchFindingsReader, type UnresolvedQuestionControls } from "./researchFindingsReader";
import { ResearchScopeEditor } from "./researchScopeEditor";

type PreparedDraft = {
  questions: readonly ResearchQuestion[];
  references: readonly { questionId: string; text: string; reason: string }[];
  revision: number;
};

function prepareDraft(references: PreparedDraft["references"], main: ResearchQuestion | undefined, revision: number): PreparedDraft {
  const selected = references.filter(({ questionId }) => questionId !== main?.question_id);
  const text = main ? [main.text, ...selected.map((question) => question.text)] : selected.map((question) => question.text);
  return {
    questions: text.map((question, index) => ({ question_id: `q${index + 1}`, text: question })),
    references,
    revision
  };
}

export type FollowUpMemory = {
  identity: string;
  selected: readonly string[];
  draft?: PreparedDraft;
  replacePending: boolean;
  revision: number;
  nextQuestionId: number;
};

/** Stateless live adapter; the child key owns context expiry and draft recovery. */
export function LiveResearchFollowUp({ language, liveRun }: {
  language: Language;
  liveRun: Pick<ReturnType<typeof useLiveRun>, "state" | "startNewRun">;
}) {
  const { state, startNewRun } = liveRun;
  const findings = state.findings;
  if (!findings) return null;

  return <ResearchFollowUp
    key={JSON.stringify([
      state.baseUrl, state.mode, state.createProfileId ?? "generic",
      findings.run_id, findings.artifact.content_hash
    ])}
    language={language}
    findings={findings}
    sourceReportVisible={state.run?.run_id === findings.run_id}
    onCancelWithoutSource={() => document.getElementById("live-known-run")?.focus()}
    disabled={state.mode !== "live" || !["result", "ready"].includes(state.status) || !state.health || Boolean(state.error)}
    onStart={(questions) => startNewRun(questions[0].text, questions, STRUCTURED_RESEARCH_PROFILE)}
  />;
}

/** Browser-local input preparation. Accepted report and creation authority stay on the service. */
export function ResearchFollowUp({ language, findings, disabled, sourceReportVisible, onCancelWithoutSource, onStart, renderReport, memory, initialQuestionId }: {
  language: Language;
  findings: ResearchFindingsResponse;
  disabled: boolean;
  sourceReportVisible: boolean;
  onCancelWithoutSource: () => void;
  onStart: (questions: readonly ResearchQuestion[]) => Promise<void>;
  renderReport?: (controls?: UnresolvedQuestionControls) => ReactNode;
  memory?: RefObject<FollowUpMemory | undefined>;
  initialQuestionId?: string;
}) {
  const t = copy[language].research;
  const identity = `${findings.run_id}/${findings.artifact.content_hash}`;
  const previous = memory?.current?.identity === identity ? memory?.current : undefined;
  const unresolved = findings.report.questions.flatMap((question) => {
    const disposition = findings.report.dispositions.find((entry) => entry.question_id === question.question_id);
    return disposition?.status === "unresolved"
      ? [{ questionId: question.question_id, text: question.text, reason: disposition.reason! }] : [];
  });
  const main = findings.report.questions[0];
  const direct = unresolved.find(({ questionId }) => questionId === initialQuestionId);
  const directSelection = direct && !previous?.draft?.references.some(({ questionId }) => questionId === direct.questionId)
    ? [direct] : undefined;
  const [selected, setSelected] = useState<readonly string[]>(() =>
    directSelection?.map(({ questionId }) => questionId) ?? previous?.selected ?? []);
  const [draft, setDraft] = useState<PreparedDraft | undefined>(() =>
    previous?.draft ?? (directSelection ? prepareDraft(directSelection, main, 1) : undefined));
  const [replacePending, setReplacePending] = useState(Boolean(directSelection && previous?.draft) || previous?.replacePending === true);
  const nextQuestionId = useRef(previous?.nextQuestionId ?? ((draft?.questions.length ?? 0) + 1));
  const revision = useRef(previous?.revision ?? draft?.revision ?? 0);
  const submitting = useRef(false);
  const draftRegion = useRef<HTMLElement>(null);
  const prepareButton = useRef<HTMLButtonElement>(null);
  const replaceButton = useRef<HTMLButtonElement>(null);
  const selectedReferences = unresolved.filter((question) => selected.includes(question.questionId));
  const scopeValid = draft && validateResearchQuestions(draft.questions).ok
    && validateLiveDemoQuery(draft.questions[0].text).ok;

  useLayoutEffect(() => {
    if (memory) memory.current = { identity, selected, draft, replacePending,
      revision: revision.current, nextQuestionId: nextQuestionId.current };
  }, [memory, identity, selected, draft, replacePending]);

  useEffect(() => {
    if (draft?.revision) {
      draftRegion.current?.querySelector<HTMLTextAreaElement>("textarea")?.focus();
      draftRegion.current?.scrollIntoView?.({ block: "start", behavior: "auto" });
    }
  }, [draft?.revision]);
  useEffect(() => {
    if (replacePending) replaceButton.current?.focus();
    else draftRegion.current?.querySelector<HTMLTextAreaElement>("textarea")?.focus();
  }, [replacePending]);

  const replaceDraft = () => {
    if (disabled || !selectedReferences.length) return;
    const prepared = prepareDraft(selectedReferences, main, ++revision.current);
    nextQuestionId.current = prepared.questions.length + 1;
    setDraft(prepared);
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

  const controls: UnresolvedQuestionControls | undefined = unresolved.length ? {
    selectedQuestionIds: selected,
    disabled,
    onToggleQuestion: (questionId) => {
      if (!disabled) setSelected((current) => current.includes(questionId)
        ? current.filter((id) => id !== questionId) : [...current, questionId]);
    },
    onPrepare: prepare,
    prepareButtonRef: prepareButton
  } : undefined;

  return <>
    {sourceReportVisible && (renderReport
      ? renderReport(controls)
      : <ResearchFindingsReader language={language} findings={findings} followUp={controls} />)}
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
          setDraft(undefined); setReplacePending(false);
          if (prepareButton.current && !prepareButton.current.disabled) prepareButton.current.focus();
          else if (prepareButton.current) prepareButton.current.closest("article")?.querySelector<HTMLInputElement>('input[type="checkbox"]:not([disabled])')?.focus();
          else onCancelWithoutSource();
        }}>{t.followUp.cancel}</button>
      </div>
    </section>}
  </>;
}
