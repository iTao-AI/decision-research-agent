import type { Ref } from "react";
import { validateLiveDemoQuery } from "../apiClient";
import type { Language } from "../i18n";
import { STRUCTURED_RESEARCH_PROFILE, type LiveResearchProfile, type ResearchQuestion } from "../researchFindings";
import { validateResearchQuestions } from "../researchScope";
import { workspaceCopy } from "../workspaceCopy";
import { ResearchScopeEditor } from "./researchScopeEditor";

export function WorkspaceDraft({ language, profile, questions, connected, busy, onProfile, onEdit, onAdd, onRemove,
  onSubmit, firstInputRef }: {
  language: Language;
  profile: LiveResearchProfile;
  questions: readonly ResearchQuestion[];
  connected: boolean;
  busy: boolean;
  onProfile: (profile: LiveResearchProfile) => void;
  onEdit: (id: string, text: string) => void;
  onAdd: () => void;
  onRemove: (id: string) => void;
  onSubmit: () => void;
  firstInputRef: Ref<HTMLTextAreaElement>;
}) {
  const t = workspaceCopy[language];
  const query = validateLiveDemoQuery(questions[0].text);
  const structured = profile === STRUCTURED_RESEARCH_PROFILE;
  const scope = structured ? validateResearchQuestions(questions) : undefined;
  const valid = query.ok && (!scope || scope.ok);
  const hint = busy ? t.otherWriteActive : !query.ok && query.reason === "blank" ? t.blank
    : scope?.ok === false && scope.reason === "blank" ? t.missingQuestion
    : !valid ? t.invalidQuestion : !connected ? t.connectToStart : undefined;
  const blank = !questions[0].text.trim();

  return <>
    <h1>{t.title}</h1>
    <p className="dw-intro">{t.intro}</p>
    <form className="dw-form" onSubmit={(event) => {
      event.preventDefault();
      if (valid && connected && !busy) onSubmit();
    }}>
      <ResearchScopeEditor language={language} disabled={false} idPrefix="dw-question"
        questions={structured ? questions : questions.slice(0, 1)}
        onEdit={onEdit} onAdd={onAdd} onRemove={onRemove}
        compact={{
          firstInputRef,
          generic: !structured,
          placeholder: t.questionPlaceholder,
          renderFooter: (addQuestion) => <div className="dw-form-footer">
            <div className="dw-form-tools">
              <select aria-label={t.mode} value={profile}
                onChange={(event) => onProfile(event.target.value as LiveResearchProfile)}>
                <option value={STRUCTURED_RESEARCH_PROFILE}>{t.evidenceMode}</option>
                <option value="generic">{t.genericMode}</option>
              </select>
              {addQuestion}
            </div>
            <button className="dw-primary" type="submit" disabled={!valid || !connected || busy}
              aria-describedby={hint ? "dw-submit-hint" : undefined}>{t.start} <span aria-hidden="true">→</span></button>
          </div>
        }} />
    </form>
    {hint && <p className="dw-hint" id="dw-submit-hint">{hint}</p>}
    {!hint && <div className="dw-hint" />}
    <div className="dw-examples">
      <button className="dw-link" type="button" disabled={!blank} onClick={() => {
        if (blank) onEdit(questions[0].question_id, t.exampleQuestion);
      }}>{t.example}</button>
      <span>{t.exampleQuestion}</span>
    </div>
  </>;
}
