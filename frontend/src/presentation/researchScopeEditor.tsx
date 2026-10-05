import { useEffect, useRef } from "react";
import { validateLiveDemoQuery } from "../apiClient";
import { copy, type Language } from "../i18n";
import type { ResearchQuestion } from "../researchFindings";
import { RESEARCH_QUESTIONS_MAX, validateResearchQuestions } from "../researchScope";

export function ResearchScopeEditor({ questions, language, disabled, onAdd, onRemove, onEdit }: {
  questions: readonly ResearchQuestion[];
  language: Language;
  disabled: boolean;
  onAdd: () => void;
  onRemove: (questionId: string) => void;
  onEdit: (questionId: string, text: string) => void;
}) {
  const t = copy[language];
  const fields = useRef(new Map<string, HTMLTextAreaElement>());
  const focusNext = useRef<string | "last" | null>(null);
  useEffect(() => {
    const next = focusNext.current;
    focusNext.current = null;
    if (next) fields.current.get(next === "last" ? questions[questions.length - 1].question_id : next)?.focus();
  }, [questions]);

  return <fieldset className="live-query-field research-scope-editor" disabled={disabled}>
    <legend>{t.research.scopeTitle}</legend>
    <small id="research-scope-hint">{t.research.scopeHint}</small>
    {questions.map((question, index) => {
      const id = `research-scope-${question.question_id}`;
      const scopeValidation = validateResearchQuestions([question]);
      const queryValidation = index === 0 ? validateLiveDemoQuery(question.text) : undefined;
      const valid = scopeValidation.ok && (!queryValidation || queryValidation.ok);
      const feedback = queryValidation && !queryValidation.ok
        ? queryValidation.reason === "blank" ? t.live.queryBlank : t.live.queryTooLarge
        : !scopeValidation.ok && scopeValidation.reason === "too_large" ? t.research.scopeTooLarge : t.research.scopeBlank;
      return <div className="research-scope-row" key={question.question_id}>
        <div className="research-scope-row-heading">
          <label htmlFor={id}>{index === 0 ? t.live.question : t.research.questionNumber(index + 1)}</label>
          <button type="button" disabled={disabled || questions.length === 1}
            aria-label={t.research.removeQuestion(index + 1)} onClick={() => {
              focusNext.current = (questions[index + 1] ?? questions[index - 1]).question_id;
              onRemove(question.question_id);
            }}>{t.research.remove}</button>
        </div>
        <textarea id={id} rows={2} disabled={disabled} value={question.text}
          ref={(element) => { if (element) fields.current.set(question.question_id, element); else fields.current.delete(question.question_id); }}
          aria-invalid={!valid} aria-describedby={`research-scope-hint ${id}-count${valid ? "" : ` ${id}-feedback`}`}
          onChange={(event) => onEdit(question.question_id, event.target.value)} />
        <small id={`${id}-count`}>{index === 0 ? t.live.queryBytes(queryValidation!.utf8Bytes) : t.research.questionPoints(Array.from(question.text).length)}</small>
        {!valid && <p className="live-query-feedback" id={`${id}-feedback`}>{feedback}</p>}
      </div>;
    })}
    <button className="research-scope-add" type="button" disabled={disabled || questions.length >= RESEARCH_QUESTIONS_MAX}
      onClick={() => { focusNext.current = "last"; onAdd(); }}>{t.research.addQuestion}</button>
  </fieldset>;
}
