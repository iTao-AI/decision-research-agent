import { useEffect, useRef, type ReactNode, type Ref } from "react";
import { validateLiveDemoQuery } from "../apiClient";
import { copy, type Language } from "../i18n";
import type { ResearchQuestion } from "../researchFindings";
import { RESEARCH_QUESTIONS_MAX, validateResearchQuestions } from "../researchScope";

export function ResearchScopeEditor({ questions, language, disabled, onAdd, onRemove, onEdit,
  idPrefix = "research-scope", legend, questionLabel, compact }: {
  questions: readonly ResearchQuestion[];
  language: Language;
  disabled: boolean;
  onAdd: () => void;
  onRemove: (questionId: string) => void;
  onEdit: (questionId: string, text: string) => void;
  idPrefix?: string;
  legend?: string;
  questionLabel?: (index: number) => string;
  compact?: {
    placeholder: string;
    generic: boolean;
    firstInputRef: Ref<HTMLTextAreaElement>;
    renderFooter: (addQuestion: ReactNode) => ReactNode;
  };
}) {
  const t = copy[language];
  const fields = useRef(new Map<string, HTMLTextAreaElement>());
  const focusNext = useRef<string | "last" | null>(null);
  useEffect(() => {
    const next = focusNext.current;
    focusNext.current = null;
    if (next) fields.current.get(next === "last" ? questions[questions.length - 1].question_id : next)?.focus();
  }, [questions]);

  const addQuestion = !compact?.generic && <button className={compact ? "dw-link" : "research-scope-add"}
    type="button" disabled={disabled || questions.length >= RESEARCH_QUESTIONS_MAX}
    onClick={() => { focusNext.current = "last"; onAdd(); }}>{t.research.addQuestion}</button>;

  return <fieldset className={`live-query-field research-scope-editor${compact ? " dw-scope-editor" : ""}`} disabled={disabled}>
    {!compact && <legend>{legend ?? t.research.scopeTitle}</legend>}
    {!compact && <small id={`${idPrefix}-hint`}>{t.research.scopeHint}</small>}
    <div className={compact ? "dw-fields" : undefined}>
    {questions.map((question, index) => {
      const id = `${idPrefix}-${question.question_id}`;
      const scopeValidation = validateResearchQuestions([question]);
      const queryValidation = index === 0 ? validateLiveDemoQuery(question.text) : undefined;
      const valid = (compact?.generic || scopeValidation.ok) && (!queryValidation || queryValidation.ok);
      const showFeedback = !valid && (!compact || Boolean(question.text.trim()));
      const describedBy = compact
        ? showFeedback ? `${id}-feedback` : undefined
        : `${idPrefix}-hint ${id}-count${valid ? "" : ` ${id}-feedback`}`;
      const feedback = queryValidation && !queryValidation.ok
        ? queryValidation.reason === "blank" ? t.live.queryBlank : t.live.queryTooLarge
        : !scopeValidation.ok && scopeValidation.reason === "too_large" ? t.research.scopeTooLarge : t.research.scopeBlank;
      return <div className="research-scope-row" key={question.question_id}>
        <div className="research-scope-row-heading">
          <label htmlFor={id}>{questionLabel ? questionLabel(index + 1) : index === 0 ? t.live.question : t.research.questionNumber(index + 1)}</label>
          {(!compact || questions.length > 1) && <button type="button" disabled={disabled || questions.length === 1}
            aria-label={t.research.removeQuestion(index + 1)} onClick={() => {
              focusNext.current = (questions[index + 1] ?? questions[index - 1]).question_id;
              onRemove(question.question_id);
            }}>{t.research.remove}</button>}
        </div>
        <textarea id={id} rows={2} disabled={disabled} value={question.text}
          placeholder={index === 0 ? compact?.placeholder : undefined}
          ref={(element) => {
            if (element) fields.current.set(question.question_id, element);
            else fields.current.delete(question.question_id);
            if (index === 0 && compact?.firstInputRef) {
              if (typeof compact.firstInputRef === "function") compact.firstInputRef(element);
              else compact.firstInputRef.current = element;
            }
          }}
          aria-invalid={showFeedback} aria-describedby={describedBy}
          onChange={(event) => onEdit(question.question_id, event.target.value)} />
        {!compact && <small id={`${id}-count`}>{index === 0 ? t.live.queryBytes(queryValidation!.utf8Bytes) : t.research.questionPoints(Array.from(question.text).length)}</small>}
        {showFeedback && <p className="live-query-feedback" id={`${id}-feedback`}>{feedback}</p>}
      </div>;
    })}
    </div>
    {compact ? compact.renderFooter(addQuestion) : addQuestion}
  </fieldset>;
}
