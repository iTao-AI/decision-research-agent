import { useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { DEFAULT_BACKEND_BASE_URL, localBackendOrigin, validateLiveRunId } from "./apiClient";
import { copy, type Language } from "./i18n";
import { ResearchFollowUp, type FollowUpMemory } from "./presentation/researchFollowUp";
import { WorkspaceDialog } from "./presentation/workspaceDialog";
import { WorkspaceDraft } from "./presentation/workspaceDraft";
import { WorkspaceDrawer } from "./presentation/workspaceDrawer";
import { WorkspaceHome } from "./presentation/workspaceHome";
import { WorkspaceReport } from "./presentation/workspaceReport";
import { WorkspaceReportOutline } from "./presentation/workspaceReportOutline";
import { shortFailureDescription } from "./presentation/workspaceRunDetails";
import { WorkspaceTaskDetails } from "./presentation/workspaceTaskDetails";
import { STRUCTURED_RESEARCH_PROFILE, type LiveResearchProfile, type ResearchFindingsResponse, type ResearchQuestion } from "./researchFindings";
import { RESEARCH_QUESTIONS_MAX } from "./researchScope";
import type { RunResultResponse } from "./runProjection";
import { useLiveRun, type LiveRunOptions, type LiveRunState } from "./useLiveRun";
import { useWorkspaceConnection } from "./useWorkspaceConnection";
import { workspaceCopy } from "./workspaceCopy";
import { trackTone, workspaceStatus, type WorkspaceStatus } from "./workspaceStatus";

type Context = "current" | "known";
type Panel = "compare" | "source" | "outline" | "follow" | "progress" | "report" | "failure" | "delivery" | "reconcile" | "known";
type Dialog = "lookup" | "settings";
type Draft = { questions: readonly ResearchQuestion[]; profile: LiveResearchProfile };
type FollowUpSource = {
  panelId: number;
  context: Context;
  report: Delivered;
  memory: RefObject<FollowUpMemory | undefined>;
};
type Submission = Draft & { followUp?: FollowUpSource };
type Delivered = { result: RunResultResponse; findings?: ResearchFindingsResponse };
type FocusReturn = { trigger: HTMLElement; scroll: number; drawer?: HTMLElement; drawerScroll?: number };
type OpenPanel = {
  id: number;
  view: Panel;
  context: Context;
  report?: Delivered;
  followMemory?: RefObject<FollowUpMemory | undefined>;
  origin: FocusReturn;
};
const EMPTY_QUESTIONS: readonly ResearchQuestion[] = [{ question_id: "q1", text: "" }];
const TERMINAL_PHASES: readonly WorkspaceStatus[] = ["delivered", "failed", "review", "blocked", "pendingDelivery"];
const ACTIVE_PHASES: readonly WorkspaceStatus[] = ["submitting", "received", "queued", "running", "reading"];

function capturePosition(trigger: HTMLElement): FocusReturn {
  const drawer = trigger.closest<HTMLElement>(".dw-drawer") ?? undefined;
  return { trigger, scroll: window.scrollY, drawer, drawerScroll: drawer?.scrollTop };
}

function deliveredReport(state: LiveRunState): Delivered | undefined {
  if (state.status !== "result" || !state.result) return undefined;
  return { result: state.result, findings: state.findings };
}

export function ResearchWorkspace({ liveOptions }: { liveOptions?: LiveRunOptions }) {
  const configuredOrigin = localBackendOrigin(import.meta.env.VITE_DRA_LOCAL_BACKEND_URL ?? "") ?? DEFAULT_BACKEND_BASE_URL;
  const current = useLiveRun(liveOptions, "live", configuredOrigin);
  const known = useLiveRun(liveOptions, "live", configuredOrigin);
  const connection = useWorkspaceConnection(current.state.baseUrl);
  const healthy = connection.status === "connected";
  const [language, setLanguage] = useState<Language>("zh");
  const t = workspaceCopy[language];
  const [questions, setQuestions] = useState(EMPTY_QUESTIONS);
  const [profile, setProfile] = useState<LiveResearchProfile>(STRUCTURED_RESEARCH_PROFILE);
  const [submitted, setSubmitted] = useState<Submission>();
  const phase = submitted ? workspaceStatus(current.state, undefined, true) : "idle";
  const currentReport = deliveredReport(current.state);
  const currentFinal = phase !== "idle" && TERMINAL_PHASES.includes(phase);
  const composing = phase === "idle" || phase === "rejected";
  const endpointLocked = [current.state.status, known.state.status].some((status) =>
    status === "creating" || status === "reconciliation_required" || status === "polling");

  const [panels, setPanels] = useState<readonly OpenPanel[]>([]);
  const [knownId, setKnownId] = useState<string>();
  const [dialog, setDialog] = useState<Dialog>();
  const [idDraft, setIdDraft] = useState("");
  const [endpointDraft, setEndpointDraft] = useState("");
  const nextQuestion = useRef(2);
  const nextPanel = useRef(1);
  const input = useRef<HTMLTextAreaElement>(null);
  const lookupButton = useRef<HTMLButtonElement>(null);
  const dialogOrigin = useRef<FocusReturn | null>(null);
  const returnAfterPaint = useRef<FocusReturn | "question" | null>(null);
  const writePending = useRef(false);
  const homeFollowUp = useRef<FollowUpMemory | undefined>(undefined);
  const knownFollowUp = useRef<FollowUpMemory | undefined>(undefined);

  useEffect(() => {
    document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
    document.title = language === "zh" ? "DRA 决策研究助手" : "DRA Decision Research Agent";
  }, [language]);

  useLayoutEffect(() => {
    const focus = returnAfterPaint.current;
    returnAfterPaint.current = null;
    if (focus === "question") {
      input.current?.focus({ preventScroll: true });
      input.current?.scrollIntoView?.({ block: "nearest" });
    } else if (focus) {
      const target = focus.trigger.isConnected ? focus.trigger : lookupButton.current;
      target?.focus({ preventScroll: true });
      if (focus.drawer?.isConnected) focus.drawer.scrollTop = focus.drawerScroll ?? 0;
      if (window.scrollY !== focus.scroll) window.scrollTo({ top: focus.scroll, behavior: "instant" });
    }
  }, [dialog, panels, questions]);

  const edit = (id: string, text: string) => setQuestions((rows) =>
    rows.map((question) => question.question_id === id ? { ...question, text } : question));
  const add = () => {
    const question_id = `q${nextQuestion.current++}`;
    setQuestions((rows) => rows.length >= RESEARCH_QUESTIONS_MAX ? rows : [...rows, { question_id, text: "" }]);
  };
  const remove = (id: string) => setQuestions((rows) =>
    rows.length < 2 ? rows : rows.filter((question) => question.question_id !== id));

  function openPanel(view: Panel, trigger: HTMLElement, context: Context = "current", report?: Delivered,
    followMemory?: OpenPanel["followMemory"]) {
    const entry: OpenPanel = { id: nextPanel.current++, view, context, report, followMemory, origin: capturePosition(trigger) };
    const fromPanel = Boolean(trigger.closest(".dw-drawer"));
    setPanels((previous) => fromPanel ? [...previous, entry] : [entry]);
  }

  function closePanel() {
    const entry = panels[panels.length - 1];
    if (!entry) return;
    returnAfterPaint.current = entry.origin;
    setPanels((previous) => previous.slice(0, -1));
  }

  function openDialog(next: Dialog, trigger: HTMLElement) {
    dialogOrigin.current = capturePosition(trigger);
    if (next === "lookup") setIdDraft("");
    else setEndpointDraft(current.state.baseUrl);
    setDialog(next);
  }

  function closeDialog(restore = true) {
    if (restore) returnAfterPaint.current = dialogOrigin.current;
    setDialog(undefined);
  }

  async function performWrite(operation: () => Promise<void>) {
    if (writePending.current) return;
    writePending.current = true;
    try { await operation(); }
    finally { writePending.current = false; }
  }

  function launch(draft: Submission) {
    return performWrite(async () => {
      setSubmitted(draft);
      await current.startNewRun(draft.questions[0].text,
        draft.profile === STRUCTURED_RESEARCH_PROFILE ? draft.questions : undefined, draft.profile);
    });
  }

  function startFresh(draft?: Draft) {
    const rows = draft?.questions ?? (submitted?.followUp !== undefined ? questions : EMPTY_QUESTIONS);
    setQuestions(rows);
    setProfile(draft?.profile ?? (submitted?.followUp !== undefined ? profile : STRUCTURED_RESEARCH_PROFILE));
    nextQuestion.current = Math.max(1, ...rows.map(({ question_id }) => Number(/^q(\d+)$/.exec(question_id)?.[1]) || 0)) + 1;
    current.discardPendingIntent();
    setSubmitted(undefined);
    setPanels([]);
    returnAfterPaint.current = "question";
  }

  function discard() {
    current.discardPendingIntent();
    setSubmitted(undefined);
    closePanel();
  }

  const draftProps = {
    language, profile, questions, connected: healthy, locked: !composing, canStartFresh: currentFinal,
    followUpRunning: submitted?.followUp !== undefined, onProfile: setProfile, onEdit: edit, onAdd: add, onRemove: remove,
    onSubmit: () => launch({ questions: profile === STRUCTURED_RESEARCH_PROFILE ? questions : questions.slice(0, 1), profile }),
    onStartFresh: () => startFresh()
  };

  const panelNames = {
    compare: t.compare, source: t.sources, outline: t.reportOutline, follow: t.follow, progress: t.progress, report: t.reportTitle,
    failure: t.viewFailure, delivery: t.viewDelivery, reconcile: t.statuses.ambiguous, known: t.existing
  };

  function renderPanel(entry: OpenPanel) {
    const { view, context, report } = entry;
    const observation = context === "current" ? current : known;
    const observedPhase = context === "current" ? (phase === "idle" ? "ready" : phase) : workspaceStatus(known.state, knownId);
    const observedId = observation.state.run?.run_id ?? observation.state.created?.run_id ?? (context === "known" ? knownId : undefined);
    const latestReport = context === "current" ? currentReport : deliveredReport(known.state);

    if (view === "outline") return <WorkspaceReportOutline language={language} />;

    if (view === "compare") {
      return <><p>{t.compareBlurb}</p><WorkspaceDraft {...draftProps} inDrawer /></>;
    }
    if (view === "report" || (view === "source" && report)) {
      const selected = report ?? latestReport;
      if (!selected) return null;
      return <>
        {view === "source" && !selected.findings && <p>{t.sourceGeneric}</p>}
        <WorkspaceReport language={language} result={selected.result} findings={selected.findings} />
        {selected.findings && <button className="dw-outline" type="button"
          onClick={(event) => openPanel("follow", event.currentTarget, context, selected)}>{t.follow}</button>}
      </>;
    }
    if (view === "follow" && report) {
      const findings = report.findings;
      const waiting = submitted?.followUp?.panelId === entry.id;
      const memory = entry.followMemory ?? (context === "known" ? knownFollowUp : homeFollowUp);
      if (!findings) return <><p>{t.followGeneric}</p><button className="dw-outline" type="button"
        onClick={(event) => openDialog("lookup", event.currentTarget)}>{t.lookupExisting}</button></>;
      const unresolved = findings.report.dispositions.filter(({ status }) => status === "unresolved");
      if (!unresolved.length) return <><p>{t.noUnresolved}</p><button className="dw-outline" type="button"
        onClick={(event) => openDialog("lookup", event.currentTarget)}>{t.lookupExisting}</button></>;
      const submittedHere = waiting && phase !== "rejected";
      return <>
        {submittedHere && <p>{t.followSubmitted}</p>}
        <ResearchFollowUp key={findings.run_id} language={language} findings={findings}
          disabled={!healthy || (!composing && !currentFinal) || submittedHere}
          memory={memory}
          sourceReportVisible onCancelWithoutSource={() => lookupButton.current?.focus()}
          onStart={(scope) => launch({ questions: scope, profile: STRUCTURED_RESEARCH_PROFILE,
            followUp: { panelId: entry.id, context, report, memory: { current: memory.current } } })}
          renderReport={(controls) => controls && <article className="dw-unresolved">
            <ol>{findings.report.questions.map((question, index) => {
              const disposition = unresolved.find(({ question_id }) => question_id === question.question_id);
              if (!disposition) return null;
              return <li key={question.question_id}>
                <label><input type="checkbox" aria-label={copy[language].research.followUp.selectQuestion(index + 1)}
                  checked={controls.selectedQuestionIds.includes(question.question_id)} disabled={controls.disabled}
                  onChange={() => controls.onToggleQuestion(question.question_id)} /> <strong>{question.text}</strong></label>
                <p>{disposition.reason}</p>
              </li>;
            })}</ol>
            <button className="dw-outline" type="button" ref={controls.prepareButtonRef}
              disabled={controls.disabled || !controls.selectedQuestionIds.length}
              onClick={controls.onPrepare}>{copy[language].research.followUp.prepare}</button>
          </article>} />
      </>;
    }
    if (view === "source" || view === "follow") {
      return <>
        <p>{view === "source" ? t.sourceBlurb : t.followBlurb}</p>
        <div className="dw-actions">
          <button className="dw-outline" type="button" onClick={(event) => openDialog("lookup", event.currentTarget)}>
            {t.lookupExisting}
          </button>
          {view === "source" && !latestReport && <button className="dw-outline" type="button"
            onClick={(event) => openPanel("outline", event.currentTarget, context)}>{t.reportOutline}</button>}
          {latestReport && <button className="dw-outline" type="button"
            onClick={(event) => openPanel(view, event.currentTarget, context, latestReport)}>
            {view === "source" ? t.currentSources : t.currentUnresolved}
          </button>}
        </div>
      </>;
    }
    if (view === "reconcile") {
      return <>
        <p>{t.statusNotes.ambiguous}</p>
        {phase === "ambiguous" ? <div className="dw-actions">
          <button className="dw-outline" type="button" onClick={() => performWrite(current.retryCreate)}>{t.retryCreate}</button>
          <button className="dw-outline" type="button" onClick={discard}>{t.discard}</button>
        </div> : <p>{phase === "idle" ? t.currentIdle : t.statuses[phase]}</p>}
      </>;
    }
    const knownTitle = latestReport?.findings?.report.questions[0]?.text;
    return <>
      {view === "known" && (knownTitle
        ? <h3 className="dw-known-title">{knownTitle}</h3>
        : observedId && <p><code>{observedId}</code></p>)}
      <WorkspaceTaskDetails language={language} state={observation.state} phase={observedPhase} runId={observedId}
        questions={context === "current" ? submitted?.questions : latestReport?.findings?.report.questions}
        onOpenDraft={context === "current" ? () => startFresh(submitted) : undefined}
        onCheckStatus={observation.resumeObservation} />
      {view === "known" && latestReport && <div className="dw-actions">
        <button className="dw-outline" type="button"
          onClick={(event) => openPanel("report", event.currentTarget, "known", latestReport)}>{t.readKnown}</button>
        <button className="dw-outline" type="button"
          onClick={(event) => openPanel("follow", event.currentTarget, "known", latestReport)}>{t.follow}</button>
      </div>}
    </>;
  }

  const tone = trackTone(phase);
  const motion = phase === "running";
  const preparing = phase === "submitting" || phase === "received" || phase === "queued";
  const icon = motion ? "" : tone === "green" ? "✓" : tone === "red" ? "×"
    : tone === "idle" ? "–" : preparing ? "◷" : tone === "blue" ? "◌" : "!";
  const reason = phase === "failed" ? shortFailureDescription(language, current.state.run?.failureCause) : undefined;
  const trackTitle = phase === "idle" ? t.idleTitle : [reason, submitted?.questions[0].text].filter(Boolean).join(" · ");
  const trackAction = phase === "delivered" ? t.readReport : phase === "failed" ? t.viewFailure
    : phase === "observeInterrupted" ? t.resume : phase === "readInterrupted" ? t.rereadReport
    : phase === "ambiguous" ? t.confirmRequest : phase === "rejected" ? t.editDraft
    : (phase === "review" || phase === "blocked" || phase === "pendingDelivery") ? t.viewDelivery
    : phase !== "idle" && ACTIVE_PHASES.includes(phase) ? t.viewProgress : undefined;
  const connectionLabel = healthy ? t.serviceConnected : connection.status === "checking" ? t.serviceChecking : t.serviceOffline;
  const lookupValid = validateLiveRunId(idDraft).ok;
  const endpointOrigin = localBackendOrigin(endpointDraft);

  return <div className="dra-workspace dw-modular dw-paper">
    <header className="dw-header">
      <div className="dw-chrome">
        <a className="dw-brand" href="/" aria-label={`DRA ${t.brand}`} onClick={(event) => {
          if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
          event.preventDefault();
          if (panels.length) {
            returnAfterPaint.current = panels[0].origin;
            setPanels([]);
          } else window.scrollTo({ top: 0 });
        }}>
          <span aria-hidden="true" className="dw-mark" />
          <span className="dw-wordmark">DRA</span><span className="dw-brand-label">{t.brand}</span>
        </a>
        <nav aria-label={t.navigation}>
          <button className="dw-link" ref={lookupButton} type="button" onClick={(event) => openDialog("lookup", event.currentTarget)}>
            {t.lookup}
          </button>
          <button className="dw-connection" type="button" data-connected={healthy} title={current.state.baseUrl}
            aria-label={`${connectionLabel}，${healthy ? t.openConnection : t.changeConnection}`}
            onClick={(event) => openDialog("settings", event.currentTarget)}>{connectionLabel}</button>
        </nav>
      </div>
    </header>
    <div className="dw-status" data-tone={tone}>
      <div className="dw-chrome">
        <span className="dw-stage">
          <span className="dw-stage-icon" aria-hidden="true">{icon}</span>
          <span role="status" aria-atomic="true">{phase === "idle" ? t.currentIdle : t.statuses[phase]}</span>
        </span>
        <span className="dw-track-title" title={trackTitle}>{trackTitle}</span>
        {trackAction && <button className="dw-track-action" type="button" onClick={(event) => {
          const trigger = event.currentTarget;
          if (phase === "delivered") openPanel("report", trigger, "current", currentReport);
          else if (phase === "failed") openPanel("failure", trigger);
          else if (phase === "observeInterrupted" || phase === "readInterrupted") void current.resumeObservation();
          else if (phase === "ambiguous") openPanel("reconcile", trigger);
          else if (phase === "rejected") {
            const follow = submitted?.followUp;
            if (follow) {
              const openFollow = panels.find(({ id }) => id === follow.panelId);
              if (openFollow) setPanels((previous) => previous.slice(0, previous.indexOf(openFollow) + 1));
              else openPanel("follow", trigger, follow.context, follow.report, follow.memory);
            } else {
              setPanels([]);
              returnAfterPaint.current = "question";
            }
          } else if (phase === "review" || phase === "blocked" || phase === "pendingDelivery") openPanel("delivery", trigger);
          else openPanel("progress", trigger);
        }}>{trackAction}</button>}
      </div>
    </div>
    {connection.status === "disconnected" && <div className="dw-connection-message dw-chrome">
      <span>{t.backend} <code>{current.state.baseUrl}</code></span>
      <button className="dw-link" type="button" onClick={(event) => openDialog("settings", event.currentTarget)}>{t.changeConnection}</button>
      <button className="dw-link" type="button" onClick={connection.retry}>{t.reconnect}</button>
    </div>}
    <div inert={panels.length > 0}>
      <WorkspaceHome language={language} onOpen={(view, trigger) =>
        openPanel(view === "outline" && currentReport ? "source" : view, trigger, "current", currentReport)}>
        <WorkspaceDraft {...draftProps} firstInputRef={input} />
      </WorkspaceHome>
    </div>
    {panels.map((entry, index) => <WorkspaceDrawer key={entry.id} title={panelNames[entry.view]}
      active={index === panels.length - 1} closeLabel={index === 0 ? t.back : t.backDetail} onClose={closePanel}>
      {renderPanel(entry)}
    </WorkspaceDrawer>)}
    {dialog === "lookup" && <WorkspaceDialog title={t.lookup} onClose={() => closeDialog()} onSubmit={(event) => {
      event.preventDefault();
      const trigger = dialogOrigin.current?.trigger;
      if (!trigger || !lookupValid || !healthy) return;
      knownFollowUp.current = undefined;
      setKnownId(idDraft);
      closeDialog(false);
      if (panels.some(({ context }) => context === "known")) setPanels([]);
      openPanel("known", trigger, "known");
      void known.attachKnownRun(idDraft);
    }}>
      <label htmlFor="dw-run-id">{t.runId}</label>
      <input id="dw-run-id" value={idDraft} onChange={(event) => setIdDraft(event.target.value)}
        aria-invalid={Boolean(idDraft) && !lookupValid} aria-describedby="dw-run-id-hint" />
      <p id="dw-run-id-hint">{idDraft && !lookupValid ? t.invalidRunId : t.runIdHint}</p>
      {!healthy && <p>{t.connectToStart}</p>}
      <div className="dw-actions">
        <button className="dw-outline" type="button" onClick={() => closeDialog()}>{t.close}</button>
        <button className="dw-primary" type="submit" disabled={!lookupValid || !healthy}>{t.open}</button>
      </div>
    </WorkspaceDialog>}
    {dialog === "settings" && <WorkspaceDialog title={t.settings} onClose={() => closeDialog()} onSubmit={(event) => {
      event.preventDefault();
      if (!endpointOrigin || endpointLocked) return;
      if (endpointOrigin === current.state.baseUrl) connection.retry();
      else {
        setPanels([]);
        setKnownId(undefined);
        setSubmitted(undefined);
        homeFollowUp.current = undefined;
        knownFollowUp.current = undefined;
        current.setBaseUrl(endpointOrigin);
        known.setBaseUrl(endpointOrigin);
        connection.retry();
      }
      closeDialog();
    }}>
      <label htmlFor="dw-backend">{t.backend}</label>
      <input id="dw-backend" value={endpointDraft} disabled={endpointLocked}
        aria-describedby="dw-backend-hint" aria-invalid={!endpointOrigin}
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
        <button className="dw-outline" type="button" onClick={connection.retry}>{t.reconnect}</button>
        <button className="dw-primary" type="submit" disabled={!endpointOrigin || endpointLocked}>{t.saveConnection}</button>
      </div>
    </WorkspaceDialog>}
  </div>;
}
