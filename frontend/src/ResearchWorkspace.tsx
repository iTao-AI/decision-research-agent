import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { localBackendOrigin, validateLiveRunId } from "./apiClient";
import { copy, type Language } from "./i18n";
import { ResearchFollowUp, type FollowUpMemory } from "./presentation/researchFollowUp";
import { WorkspaceDialog } from "./presentation/workspaceDialog";
import { WorkspaceDraft } from "./presentation/workspaceDraft";
import { WorkspaceReport } from "./presentation/workspaceReport";
import { failureDescription, WorkspaceRetainedEvidence, WorkspaceRunDetails } from "./presentation/workspaceRunDetails";
import { STRUCTURED_RESEARCH_PROFILE, type LiveResearchProfile, type ResearchQuestion } from "./researchFindings";
import { RESEARCH_QUESTIONS_MAX } from "./researchScope";
import { useLiveRun, type LiveRunOptions } from "./useLiveRun";
import { workspaceCopy } from "./workspaceCopy";
import { statusTone, workspaceStatus, type WorkspaceStatus } from "./workspaceStatus";

type View = "home" | "known";
type Dialog = "lookup" | "settings";
type Submitted = { questions: readonly ResearchQuestion[]; profile: LiveResearchProfile };
const EMPTY_QUESTIONS: readonly ResearchQuestion[] = [{ question_id: "q1", text: "" }];
const DRAFT_STATUSES: readonly WorkspaceStatus[] = ["connecting", "ready", "offline", "rejected"];
const AUTOPOLL_STATUSES: readonly WorkspaceStatus[] = ["received", "lookup", "queued", "running", "reading"];
const SERVICE_OUTCOME_STATUSES: readonly WorkspaceStatus[] = ["failed", "review", "blocked", "pendingDelivery"];

function focusSection(element: HTMLElement | null) {
  element?.focus({ preventScroll: true });
  element?.scrollIntoView?.({ block: "start" });
}

export function ResearchWorkspace({ liveOptions }: { liveOptions?: LiveRunOptions }) {
  const home = useLiveRun(liveOptions, "live");
  const known = useLiveRun(liveOptions, "live");
  const [view, setView] = useState<View>("home");
  const live = view === "home" ? home : known;
  const { state } = live;
  const [language, setLanguage] = useState<Language>("zh");
  const t = workspaceCopy[language];
  const [questions, setQuestions] = useState(EMPTY_QUESTIONS);
  const [profile, setProfile] = useState<LiveResearchProfile>(STRUCTURED_RESEARCH_PROFILE);
  const [submitted, setSubmitted] = useState<Partial<Record<View, Submitted>>>({});
  const submittedHere = submitted[view];
  const [knownId, setKnownId] = useState<string>();
  const observedId = view === "known" ? knownId : undefined;
  const runId = state.run?.run_id ?? state.created?.run_id ?? observedId;
  const phase = workspaceStatus(state, observedId);
  const [dialog, setDialog] = useState<Dialog>();
  const [idDraft, setIdDraft] = useState("");
  const [endpointDraft, setEndpointDraft] = useState("");
  const nextQuestion = useRef(2);
  const questionRef = useRef<HTMLTextAreaElement>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const reportRef = useRef<HTMLElement>(null);
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const dialogTrigger = useRef<HTMLElement>(null);
  const restoreDialogFocus = useRef(false);
  const writeInProgress = useRef(false);
  const homeFollowUp = useRef<FollowUpMemory | undefined>(undefined);
  const knownFollowUp = useRef<FollowUpMemory | undefined>(undefined);
  const focusOnDraft = useRef(false);
  const focusOnRun = useRef(false);
  const focusOnReturn = useRef(false);
  const lookupButton = useRef<HTMLButtonElement>(null);

  const checkHealth = home.checkHealth;
  useEffect(() => {
    const timer = window.setTimeout(() => { void checkHealth(); }, 0);
    return () => window.clearTimeout(timer);
  }, [checkHealth]);
  useEffect(() => {
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  }, [language]);
  useEffect(() => {
    if (focusOnDraft.current && questionRef.current) {
      focusOnDraft.current = false;
      focusSection(questionRef.current);
    }
    if (focusOnRun.current && headingRef.current) {
      focusOnRun.current = false;
      focusSection(headingRef.current);
    }
    if (focusOnReturn.current && view === "home") {
      focusOnReturn.current = false;
      lookupButton.current?.focus();
    }
  }, [view, phase]);

  useLayoutEffect(() => {
    if (!dialog && restoreDialogFocus.current) {
      restoreDialogFocus.current = false;
      dialogTrigger.current?.focus();
    }
  }, [dialog]);

  const healthy = Boolean(home.state.health);
  const showDraft = view === "home" && DRAFT_STATUSES.includes(phase) && !state.findings;
  const endpointLocked = [home.state, known.state].some(({ status }) =>
    status === "creating" || status === "reconciliation_required" || status === "polling");
  const knownWriteActive = known.state.status === "creating" || known.state.status === "reconciliation_required"
    || (known.state.status === "polling" && Boolean(known.state.created));
  const returnToKnown = view === "home" && Boolean(submitted.known);
  const lookupLocked = view === "known" && knownWriteActive;
  const terminal = SERVICE_OUTCOME_STATUSES.includes(phase);
  const canStartFresh = view === "home" || !endpointLocked;
  const acceptedQuestions = state.status === "result" ? state.findings?.report.questions : undefined;
  const title = acceptedQuestions?.[0].text ?? submittedHere?.questions[0].text ?? (view === "home" ? t.current : t.existing);
  const draftOrigin = submittedHere ?? (acceptedQuestions
    ? { questions: acceptedQuestions, profile: STRUCTURED_RESEARCH_PROFILE } : undefined);

  const editQuestion = (id: string, text: string) => setQuestions((current) =>
    current.map((question) => question.question_id === id ? { ...question, text } : question));
  const addQuestion = () => {
    const question_id = `q${nextQuestion.current++}`;
    setQuestions((current) => current.length >= RESEARCH_QUESTIONS_MAX
      ? current : [...current, { question_id, text: "" }]);
  };
  const removeQuestion = (id: string) => setQuestions((current) =>
    current.length < 2 ? current : current.filter((question) => question.question_id !== id));

  async function performWrite(operation: () => Promise<void>) {
    if (writeInProgress.current) return;
    writeInProgress.current = true;
    try { await operation(); }
    finally { writeInProgress.current = false; }
  }

  function launch(draft: Submitted) {
    return performWrite(async () => {
      setSubmitted((current) => ({ ...current, [view]: draft }));
      setKnownId((current) => view === "known" ? undefined : current);
      focusOnRun.current = true;
      await live.startNewRun(draft.questions[0].text,
        draft.profile === STRUCTURED_RESEARCH_PROFILE ? draft.questions : undefined, draft.profile);
    });
  }

  const closeDialog = (restoreFocus = true) => {
    restoreDialogFocus.current = restoreFocus;
    setDialog(undefined);
  };

  const openLookup = (trigger: HTMLElement) => {
    dialogTrigger.current = trigger;
    setIdDraft("");
    setDialog("lookup");
  };

  const startFresh = (draft?: Submitted) => {
    const rows = draft?.questions ?? EMPTY_QUESTIONS;
    setQuestions(rows);
    setProfile(draft?.profile ?? STRUCTURED_RESEARCH_PROFILE);
    nextQuestion.current = Math.max(1, ...rows.map(({ question_id }) => Number(/^q(\d+)$/.exec(question_id)?.[1]) || 0)) + 1;
    setSubmitted((current) => view === "known" ? {} : { ...current, home: undefined });
    homeFollowUp.current = undefined;
    focusOnDraft.current = true;
    if (view === "known") {
      knownFollowUp.current = undefined;
      known.discardPendingIntent();
      setKnownId(undefined);
      setView("home");
    }
    home.discardPendingIntent();
    if (!healthy && home.state.status !== "checking") void checkHealth();
  };

  const backToWorkspace = () => {
    focusOnReturn.current = true;
    setView("home");
  };

  function openDetails() {
    if (detailsRef.current) {
      detailsRef.current.open = true;
      focusSection(detailsRef.current.querySelector("summary"));
    }
  }

  let actions: ReactNode;
  switch (phase) {
    case "offline":
      actions = <button className="dw-link" type="button" onClick={checkHealth}>{t.reconnect}</button>;
      break;
    case "ambiguous":
      actions = <>
        <button className="dw-link" type="button" onClick={() => performWrite(live.retryCreate)}>{t.retryCreate}</button>
        <button className="dw-link" type="button" onClick={() => {
          live.discardPendingIntent();
          if (view === "known") {
            setSubmitted((current) => ({ ...current, known: undefined }));
            knownFollowUp.current = undefined;
            backToWorkspace();
          } else {
            homeFollowUp.current = undefined;
          }
        }}>{t.discard}</button>
      </>;
      break;
    case "readInterrupted":
    case "observeInterrupted":
      actions = <button className="dw-link" type="button" onClick={live.resumeObservation}>{t.resume}</button>;
      break;
    case "review":
    case "blocked":
    case "pendingDelivery":
      actions = <button className="dw-link" type="button" onClick={live.resumeObservation}>{t.checkRun}</button>;
      break;
    case "delivered":
      actions = <button className="dw-link" type="button" onClick={() => focusSection(reportRef.current)}>{t.readReport}</button>;
      break;
    default:
      if (runId) actions = <button className="dw-link" type="button" onClick={openDetails}>{t.details}</button>;
  }
  const statusNote = t.statusNotes[phase as keyof typeof t.statusNotes]
    ?? (AUTOPOLL_STATUSES.includes(phase) ? t.automatic : undefined);
  const lookupValidation = validateLiveRunId(idDraft);
  const savedOrigin = localBackendOrigin(endpointDraft);
  const report = state.status === "result" ? state.result : undefined;
  const followUpAllowed = healthy && (phase === "delivered" || phase === "rejected")
    && (view !== "known" || !["ambiguous", "submitting", ...AUTOPOLL_STATUSES].includes(workspaceStatus(home.state)));

  return <div className="dra-workspace">
    <header className="dw-header">
      <div className="dw-chrome">
        <a className="dw-brand" href="/" onClick={(event) => {
          if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
          event.preventDefault();
          if (view === "known") backToWorkspace();
          else window.scrollTo({ top: 0 });
        }}>
          <span aria-hidden="true" className="dw-mark" />
          <span className="dw-wordmark">DRA</span><span className="dw-brand-label">{t.brand}</span>
        </a>
        <nav aria-label={t.navigation}>
          <button className="dw-link" ref={lookupButton} type="button" disabled={lookupLocked}
            onClick={(event) => {
              if (returnToKnown) {
                focusOnRun.current = true;
                setView("known");
              } else openLookup(event.currentTarget);
            }}>{returnToKnown ? t.returnToKnown : t.lookup}</button>
          <a className="dw-link" href="/?showcase=overview" target="_blank" rel="noopener">
            {t.showcase} <span aria-hidden="true">↗</span>
          </a>
          <button className="dw-outline" type="button" onClick={(event) => {
            dialogTrigger.current = event.currentTarget;
            setEndpointDraft(home.state.baseUrl);
            setDialog("settings");
          }}>{t.settings}</button>
        </nav>
      </div>
      <div className="dw-status" data-tone={statusTone(phase)}>
        <div className="dw-chrome">
          <div className="dw-status-text" role="status" aria-atomic="true">
            <span className="dw-dot" aria-hidden="true" />
            <strong>{t.statuses[phase]}</strong>
            {statusNote && <span className="dw-status-note">{statusNote}</span>}
          </div>
          <div className="dw-actions">{actions}</div>
        </div>
      </div>
    </header>
    <main className="dw-main">
      <div className={`dw-page${report ? "" : " dw-editor"}`}>
        {showDraft ? <WorkspaceDraft language={language} connected={healthy} busy={knownWriteActive}
          profile={profile} onProfile={setProfile} questions={questions}
          onEdit={editQuestion} onAdd={addQuestion} onRemove={removeQuestion} firstInputRef={questionRef}
          onSubmit={() => launch({ profile, questions: profile === STRUCTURED_RESEARCH_PROFILE ? questions : questions.slice(0, 1) })} />
        : <>
          {view === "known" && <button className="dw-link dw-back" type="button" onClick={backToWorkspace}>{t.back}</button>}
          <h1 ref={headingRef} tabIndex={-1}>{title}</h1>
          {submittedHere && !report && submittedHere.questions.length > 1 && <ul className="dw-question-list">
            {submittedHere.questions.slice(1).map((question) => <li key={question.question_id}>{question.text}</li>)}
          </ul>}
          {AUTOPOLL_STATUSES.includes(phase) && (state.created || state.run) && <section className="dw-events" aria-label={t.progress}>
            <h2>{t.progress}</h2>
            <ol>
              {state.created && <li>{t.requested}</li>}
              {state.run && <li>{t.statuses[phase]}</li>}
            </ol>
          </section>}
          {terminal && state.run && <section className="dw-notice" data-tone={statusTone(phase)}>
            {phase === "failed" ? <>
              <h2>{failureDescription(language, state.run.failureCause)}</h2>
              <p>{t.resultUnavailable}</p>
            </> : <p>{phase === "review" ? t.reviewPending : phase === "blocked" ? t.deliveryBlocked : t.deliveryPending}</p>}
            <WorkspaceRetainedEvidence language={language} run={state.run} />
            {canStartFresh && phase === "failed" && <button className="dw-outline" type="button"
              onClick={() => startFresh(draftOrigin)}>{draftOrigin ? t.editAgain : t.newResearch}</button>}
          </section>}
          {state.findings ? <ResearchFollowUp key={`${view}/${state.findings.run_id}/${state.findings.artifact.content_hash}`}
            language={language} findings={state.findings} disabled={!followUpAllowed}
            memory={view === "home" ? homeFollowUp : knownFollowUp}
            sourceReportVisible={Boolean(report)} onCancelWithoutSource={() => lookupButton.current?.focus()}
            onStart={(scope) => launch({ questions: scope, profile: STRUCTURED_RESEARCH_PROFILE })}
            renderReport={(controls) => report && <WorkspaceReport language={language} result={report}
              findings={state.findings} followUp={controls} reportRef={reportRef} />} />
            : report && <WorkspaceReport language={language} result={report} reportRef={reportRef} />}
          {view === "home" && ["delivered", "blocked", "review", "pendingDelivery"].includes(phase)
            && <button className="dw-outline dw-new" type="button" onClick={() => startFresh()}>{t.newResearch}</button>}
        </>}
        {(runId || state.error) && <WorkspaceRunDetails key={`${view}/${runId ?? "none"}`} language={language}
          state={state} runId={runId} detailsRef={detailsRef} />}
      </div>
    </main>
    {dialog === "lookup" && <WorkspaceDialog title={t.lookup} onClose={() => closeDialog()} onSubmit={(event) => {
      event.preventDefault();
      if (!lookupValidation.ok || !healthy || lookupLocked) return;
      setSubmitted((current) => ({ ...current, known: undefined }));
      knownFollowUp.current = undefined;
      setKnownId(idDraft);
      setView("known");
      focusOnRun.current = true;
      closeDialog(false);
      void known.attachKnownRun(idDraft);
    }}>
      <label htmlFor="dw-run-id">{t.runId}</label>
      <input id="dw-run-id" value={idDraft} onChange={(event) => setIdDraft(event.target.value)}
        aria-invalid={Boolean(idDraft) && !lookupValidation.ok} aria-describedby="dw-run-id-hint" />
      <p id="dw-run-id-hint">{idDraft && !lookupValidation.ok ? t.invalidRunId : t.runIdHint}</p>
      {!healthy && <p>{t.connectToStart}</p>}
      <div className="dw-actions">
        <button className="dw-outline" type="button" onClick={() => closeDialog()}>{t.close}</button>
        <button className="dw-primary" type="submit" disabled={!lookupValidation.ok || !healthy || lookupLocked}>{t.open}</button>
      </div>
    </WorkspaceDialog>}
    {dialog === "settings" && <WorkspaceDialog title={t.settings} onClose={() => closeDialog()} onSubmit={(event) => {
      event.preventDefault();
      if (!savedOrigin || endpointLocked) return;
      if (savedOrigin === home.state.baseUrl) {
        if (["offline", "connecting"].includes(workspaceStatus(home.state))) void checkHealth();
      } else {
        setView("home");
        setKnownId(undefined);
        setSubmitted({});
        homeFollowUp.current = undefined;
        knownFollowUp.current = undefined;
        home.setBaseUrl(savedOrigin);
        known.setBaseUrl(savedOrigin);
      }
      closeDialog();
    }}>
      <label htmlFor="dw-backend">{t.backend}</label>
      <input id="dw-backend" value={endpointDraft} disabled={endpointLocked}
        aria-describedby="dw-backend-hint" aria-invalid={!savedOrigin}
        onChange={(event) => setEndpointDraft(event.target.value)} />
      <p id="dw-backend-hint">{t.backendHint}</p>
      <div className="dw-actions" role="group" aria-label={t.language}>
        <button className="dw-outline" type="button" aria-pressed={language === "zh"} onClick={() => setLanguage("zh")}>
          {copy[language].chinese}
        </button>
        <button className="dw-outline" type="button" aria-pressed={language === "en"} onClick={() => setLanguage("en")}>
          {copy[language].english}
        </button>
      </div>
      <div className="dw-actions">
        <button className="dw-outline" type="button" onClick={() => closeDialog()}>{t.close}</button>
        <button className="dw-primary" type="submit" disabled={!savedOrigin || endpointLocked}>{t.saveConnection}</button>
      </div>
    </WorkspaceDialog>}
  </div>;
}
