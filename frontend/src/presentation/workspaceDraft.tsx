import type { Ref } from "react";
import { validateLiveDemoQuery } from "../apiClient";
import type { Language } from "../i18n";
import { STRUCTURED_RESEARCH_PROFILE, type LiveResearchProfile, type ResearchQuestion } from "../researchFindings";
import { validateResearchQuestions } from "../researchScope";
import { workspaceCopy } from "../workspaceCopy";
import { ResearchScopeEditor } from "./researchScopeEditor";

export function WorkspaceDraft({ language, profile, questions, connected, locked, canStartFresh, followUpRunning,
  onProfile, onEdit, onAdd, onRemove, onSubmit, onStartFresh, firstInputRef, inDrawer = false }: {
  language: Language;
  profile: LiveResearchProfile;
  questions: readonly ResearchQuestion[];
  connected: boolean;
  locked: boolean;
  canStartFresh: boolean;
  followUpRunning: boolean;
  onProfile: (profile: LiveResearchProfile) => void;
  onEdit: (id: string, text: string) => void;
  onAdd: () => void;
  onRemove: (id: string) => void;
  onSubmit: () => void;
  onStartFresh: () => void;
  firstInputRef?: Ref<HTMLTextAreaElement>;
  inDrawer?: boolean;
}) {
  const t = workspaceCopy[language];
  const query = validateLiveDemoQuery(questions[0].text);
  const structured = profile === STRUCTURED_RESEARCH_PROFILE;
  const scope = structured ? validateResearchQuestions(questions) : undefined;
  const valid = query.ok && (!scope || scope.ok);
  const allowed = canStartFresh || (!locked && valid && connected);
  const hint = locked ? (followUpRunning ? t.otherWriteActive : t.draftLocked)
    : !connected ? t.connectToStart : !query.ok && query.reason === "blank" ? t.blank
    : scope?.ok === false && scope.reason === "blank" ? t.missingQuestion
    : !valid ? t.invalidQuestion : t.validDraft;
  const id = inDrawer ? "dw-compare-question" : "dw-question";

  return <form className={inDrawer ? "dw-form dw-compare-form" : "dw-form dw-composer"} onSubmit={(event) => {
    event.preventDefault();
    if (!allowed) return;
    if (canStartFresh) onStartFresh();
    else onSubmit();
  }}>
    {!inDrawer && <h2 className="dw-composer-heading">{t.compose}</h2>}
    <ResearchScopeEditor language={language} disabled={false} idPrefix={id}
      questions={structured ? questions : questions.slice(0, 1)}
      onEdit={onEdit} onAdd={onAdd} onRemove={onRemove}
      compact={{
        firstInputRef, generic: !structured, placeholder: t.questionPlaceholder, readOnly: locked, addLabel: t.addQuestion,
        renderFooter: (addQuestion) => <div className="dw-form-footer">
          <div className="dw-form-tools">
            {addQuestion}
            <select aria-label={t.mode} value={profile} disabled={locked || (structured && questions.length > 1)}
              onChange={(event) => onProfile(event.target.value as LiveResearchProfile)}>
              <option value={STRUCTURED_RESEARCH_PROFILE}>{t.evidenceMode}</option>
              <option value="generic">{t.genericMode}</option>
            </select>
          </div>
          <div className="dw-form-end">
            <p className="dw-hint" id={`${id}-submit-hint`}>{hint}</p>
            <button className="dw-primary" type="submit" aria-disabled={!allowed}
              aria-describedby={`${id}-submit-hint`}>
              {canStartFresh ? t.newResearch : locked ? t.submitted : t.start}
              {!locked && <span aria-hidden="true">↗</span>}
            </button>
          </div>
        </div>
      }} />
  </form>;
}
