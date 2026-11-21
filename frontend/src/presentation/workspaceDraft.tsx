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
    : !valid ? t.invalidQuestion : undefined;
  const id = inDrawer ? "dw-compare-question" : "dw-question";

  const hintId = `${id}-submit-hint`;
  const hintText = <p className="dw-hint" id={hintId}>{hint}</p>;
  const submit = <button className="dw-primary" type="submit" aria-disabled={!allowed} aria-describedby={hint ? hintId : undefined}>
    {canStartFresh ? t.newResearch : locked ? t.submitted : t.start}
    {!locked && <span aria-hidden="true">→</span>}
  </button>;

  return <form className={inDrawer ? "dw-form dw-compare-form" : "dw-form dw-composer"} aria-label={t.compose}
    onSubmit={(event) => {
      event.preventDefault();
      if (!allowed) return;
      if (canStartFresh) onStartFresh();
      else onSubmit();
    }}>
    <ResearchScopeEditor language={language} disabled={false} idPrefix={id}
      questions={structured ? questions : questions.slice(0, 1)}
      onEdit={onEdit} onAdd={onAdd} onRemove={onRemove}
      compact={{
        firstInputRef, generic: !structured, placeholder: t.questionPlaceholder, readOnly: locked, addLabel: t.addQuestion,
        addText: inDrawer ? undefined : t.subquestions,
        renderFooter: (addQuestion) => <div className="dw-form-footer">
          <div className="dw-form-tools">
            {addQuestion}
            <select aria-label={t.mode} value={profile} disabled={locked || (structured && questions.length > 1)}
              onChange={(event) => onProfile(event.target.value as LiveResearchProfile)}>
              <option value={STRUCTURED_RESEARCH_PROFILE}>{t.evidenceMode}</option>
              <option value="generic">{t.genericMode}</option>
            </select>
            {!inDrawer && submit}
          </div>
          {inDrawer && <div className="dw-form-end">{hintText}{submit}</div>}
        </div>
      }} />
    {!inDrawer && hintText}
  </form>;
}
