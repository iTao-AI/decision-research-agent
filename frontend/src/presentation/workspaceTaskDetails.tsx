import { useId } from "react";
import type { Language } from "../i18n";
import type { ResearchQuestion } from "../researchFindings";
import type { RunProjection } from "../runProjection";
import type { LiveRunState } from "../useLiveRun";
import { workspaceCopy } from "../workspaceCopy";
import { statusTone, type WorkspaceStatus } from "../workspaceStatus";
import { failureDescription, WorkspaceRetainedEvidence, WorkspaceRunDetails } from "./workspaceRunDetails";

type WorkspaceTaskDetailsProps = {
  language: Language;
  state: LiveRunState;
  phase: WorkspaceStatus;
  runId?: string;
  questions?: readonly ResearchQuestion[];
  onOpenDraft?: () => void;
  onCheckStatus?: () => void;
};

const detailCopy = {
  zh: {
    stopPhase: "停止阶段", stopReason: "停止原因", phaseUnknown: "服务端未提供停止阶段。",
    failurePhases: { dispatch: "启动", execution: "执行", finalization: "结果收尾" },
    questions: "本次研究问题", receiptReplayed: "服务端返回了同一提交的回执。",
    blocked: "研究已结束。服务端显示交付受阻，暂无可阅读的报告。",
    citationBlocked: "研究已结束，部分引文无法在已保存的摘录中定位，报告未生成。",
    citationRejected: "研究已结束，部分报告引文无法绑定到来源，报告未生成。",
    excerptCount: (count: number) => `有 ${count} 处引文定位失败。`,
    bindingCount: (count: number) => `有 ${count} 处引文绑定失败。`,
    emptyBlocked: "研究已结束，未形成可用于交付的结论，报告未生成。"
  },
  en: {
    stopPhase: "Stop phase", stopReason: "Stop reason", phaseUnknown: "The service provided no stop phase.",
    failurePhases: { dispatch: "Dispatch", execution: "Execution", finalization: "Finalization" },
    questions: "Research questions", receiptReplayed: "The service returned the receipt for the same submission.",
    blocked: "Research finished. The service reports that delivery is blocked. No report is available.",
    citationBlocked: "Research finished. Some citations could not be matched to saved excerpts, so no report was generated.",
    citationRejected: "Research finished. Some citations could not be bound to sources, so no report was generated.",
    excerptCount: (count: number) => count === 1 ? "1 citation match failed." : `${count} citation matches failed.`,
    bindingCount: (count: number) => count === 1 ? "1 citation binding failed." : `${count} citation bindings failed.`,
    emptyBlocked: "Research finished without findings suitable for delivery, so no report was generated."
  }
};

const EXCERPT_ISSUES = new Set(["excerpt_not_found", "ambiguous_reference"]);
const CITATION_ISSUES = new Set([
  ...EXCERPT_ISSUES, "source_url_not_publishable", "source_not_observed", "reference_binding_failed"
]);

function WorkspaceBlockedReason({ language, run }: { language: Language; run?: RunProjection }) {
  const labels = detailCopy[language];
  const count = run?.findingsOutcome?.reference_binding_failure_count ?? 0;
  const issues = run?.findingsIssues;
  if (count > 0 || issues?.some((issue) => CITATION_ISSUES.has(issue))) {
    const excerptsOnly = issues?.length && issues.every((issue) => EXCERPT_ISSUES.has(issue));
    return <>
      <p className="dw-delivery-reason">{excerptsOnly ? labels.citationBlocked : labels.citationRejected}</p>
      {count > 0 && <p>{excerptsOnly ? labels.excerptCount(count) : labels.bindingCount(count)}</p>}
    </>;
  }
  const description = run?.findingsIssues?.includes("empty_research_output") ? labels.emptyBlocked : labels.blocked;
  return <p className="dw-delivery-reason">{description}</p>;
}

export function WorkspaceTaskDetails({
  language, state, phase, runId, questions, onOpenDraft, onCheckStatus
}: WorkspaceTaskDetailsProps) {
  const t = workspaceCopy[language];
  const labels = detailCopy[language];
  const headingId = useId();
  const questionsId = useId();
  const { created, run } = state;
  const observedRunId = run?.run_id ?? created?.run_id ?? runId;
  const failure = run?.failureCause;
  const observedFailure = failure?.kind === "observed" ? failure : undefined;
  const failurePhase = observedFailure?.phase as keyof typeof labels.failurePhases | undefined;
  const deliveryNote = {
    review: t.reviewPending, pendingDelivery: t.deliveryPending
  };
  const delivery = phase === "review" || phase === "blocked" || phase === "pendingDelivery";
  const interrupted = phase === "readInterrupted" || phase === "observeInterrupted";
  const finalBlocked = phase === "blocked" && run?.review_status === "not_required";
  const note = t.statusNotes[phase as keyof typeof t.statusNotes];
  const activeRead = phase === "received" || phase === "lookup" || phase === "queued" ||
    phase === "running" || phase === "reading";
  const checkLabel = phase === "readInterrupted" ? t.rereadReport : interrupted ? t.resume : t.checkRun;
  const draftLabel = phase === "rejected" ? t.editDraft : questions?.length ? t.editAgain : t.newResearch;

  return <div className="dw-task-details">
    <section className="dw-notice" data-tone={statusTone(phase)} aria-labelledby={headingId}>
      <h3 id={headingId}>{t.statuses[phase]}</h3>
      {phase === "failed" ? <>
        <dl>
          <div><dt>{labels.stopPhase}</dt>
            <dd>{failurePhase ? labels.failurePhases[failurePhase] : labels.phaseUnknown}</dd></div>
          <div><dt>{labels.stopReason}</dt><dd>
            <p>{failureDescription(language, failure)}</p>
            {observedFailure && <code>{observedFailure.code}</code>}
          </dd></div>
        </dl>
        <p>{t.resultUnavailable}</p>
      </> : phase === "blocked" ? <WorkspaceBlockedReason language={language} run={run} /> : <>
        {created && phase !== "received" && <p>{t.requested}</p>}
        {created?.idempotent_replay && <p>{labels.receiptReplayed}</p>}
        {(phase === "review" || phase === "pendingDelivery") && <p>{deliveryNote[phase]}</p>}
        {note && <p>{note}</p>}
        {activeRead && <p>{t.automatic}</p>}
        {(delivery || interrupted) && run && <dl>
          <div><dt>{t.execution}</dt><dd><code>{run.execution_status}</code></dd></div>
          <div><dt>{t.delivery}</dt><dd><code>{run.delivery_status}</code></dd></div>
        </dl>}
      </>}
      {(phase === "failed" || delivery || interrupted) && run && <WorkspaceRetainedEvidence key={run.run_id} language={language} run={run} />}
      {(phase === "failed" || phase === "rejected") && onOpenDraft && <div className="dw-actions">
        <button className="dw-outline" type="button" onClick={onOpenDraft}>{draftLabel}</button>
      </div>}
      {((delivery && !finalBlocked) || interrupted) && observedRunId && onCheckStatus && <div className="dw-actions">
        <button className="dw-outline" type="button" onClick={onCheckStatus}>{checkLabel}</button>
      </div>}
    </section>
    {questions && questions.length > 0 && <section aria-labelledby={questionsId}>
      <h3 id={questionsId}>{labels.questions}</h3>
      <ol className="dw-question-list">
        {questions.map(({ question_id, text }) => <li key={question_id}>{text}</li>)}
      </ol>
    </section>}
    {(observedRunId || state.error) && <WorkspaceRunDetails language={language} state={state} runId={observedRunId} />}
  </div>;
}
