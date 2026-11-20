import { useState, type Ref } from "react";
import { buildLiveConsoleProjection } from "../consoleProjection";
import { copy, type Language } from "../i18n";
import type { RunProjection } from "../runProjection";
import type { LiveRunState } from "../useLiveRun";
import { workspaceCopy } from "../workspaceCopy";
import { safeHttpUrl } from "./resultReader";
import { ArchitectureMode } from "./technicalScreens";

const architectureReference = buildLiveConsoleProjection({
  health: undefined, created: undefined, run: undefined, result: undefined, status: "idle"
});

export function WorkspaceRunDetails({ language, state, runId, detailsRef }: {
  language: Language;
  state: LiveRunState;
  runId?: string;
  detailsRef: Ref<HTMLDetailsElement>;
}) {
  const t = workspaceCopy[language];
  const [copiedId, setCopiedId] = useState("");
  const run = state.run;
  const failure = run?.failureCause;
  const review = run?.review.workflow;
  const publication = run?.currentPublication;
  return <details className="dw-details" ref={detailsRef}>
    <summary>{t.details}</summary>
    <dl>
      {runId && <div><dt>{t.runId}</dt><dd><code id="dw-current-run-id">{runId}</code>
        <button className="dw-link" type="button" onClick={async () => {
          try {
            await navigator.clipboard.writeText(runId);
            setCopiedId(runId);
          } catch {
            const id = document.getElementById("dw-current-run-id");
            if (id) document.getSelection()?.selectAllChildren(id);
          }
        }}>{copiedId === runId ? t.copied : t.copyRun}</button>
      </dd></div>}
      {run && <>
        <div><dt>{t.profile}</dt><dd><code>{run.profile_id}</code></dd></div>
        <div><dt>{t.execution}</dt><dd><code>{run.execution_status}</code></dd></div>
        <div><dt>{t.delivery}</dt><dd><code>{run.delivery_status}</code></dd></div>
        <div><dt>{copy[language].labels.review}</dt><dd><code>{review?.status ?? run.review_status}</code></dd></div>
      </>}
      {failure?.kind === "observed" && <div><dt>{t.failureObserved}</dt><dd><code>{failure.phase} / {failure.code}</code></dd></div>}
      {state.error && <div><dt>{t.errorCode}</dt><dd><code>{state.error.code}</code></dd></div>}
      {publication && <div><dt>{t.publication}</dt><dd><code>{publication.status}</code></dd></div>}
      {run?.currentArtifacts?.map((artifact) => <div key={artifact.artifact_id}>
        <dt>{artifact.kind}</dt><dd><code>{artifact.artifact_id}</code> <small>{artifact.content_hash}</small></dd>
      </div>)}
    </dl>
    {(run?.findingsIssues || run?.findingsOutcome) && <section aria-label={copy[language].research.diagnostics}>
      <h3>{copy[language].research.diagnostics}</h3>
      {run.findingsIssues && <ul>{run.findingsIssues.map((issue) => <li key={issue}><code>{issue}</code></li>)}</ul>}
      {run.findingsOutcome && <>
        <p>{copy[language].research.counts}</p>
        <dl>{Object.entries(run.findingsOutcome).map(([key, count]) => <div key={key}>
          <dt><code>{key}</code></dt><dd>{count}</dd>
        </div>)}</dl>
      </>}
    </section>}
    <details className="dw-details">
      <summary>{t.architecture}</summary>
      <ArchitectureMode language={language} projection={architectureReference} />
      <h3>{copy[language].labels.cli}</h3>
      <pre>{architectureReference.architecture.cliGoldenPath}</pre>
    </details>
  </details>;
}

export function WorkspaceRetainedEvidence({ language, run }: { language: Language; run: RunProjection }) {
  const t = workspaceCopy[language];
  if (!run.evidence.length) return <p>{t.noEvidence}</p>;
  return <details className="dw-details dw-retained-sources">
    <summary>{t.stateEvidence(run.evidence.length)}</summary>
    <ul>{run.evidence.map((evidence) => {
      const href = evidence.source_url ? safeHttpUrl(evidence.source_url) : undefined;
      const name = evidence.source_identity || evidence.evidence_id;
      return <li key={evidence.evidence_id}>
        {href ? <a href={href} target="_blank" rel="noreferrer">{name}</a> : name}
      </li>;
    })}</ul>
  </details>;
}

export function failureDescription(language: Language, failure: RunProjection["failureCause"] | undefined) {
  const t = workspaceCopy[language];
  if (failure?.kind !== "observed") return t.failureUnknown;
  if (failure.code === "cancelled") return t.failureCancelled;
  if (failure.code === "run_timeout") return failure.phase === "finalization" ? t.finalizeTimeout : t.failureTimeout;
  if (failure.phase === "dispatch") return t.failureDispatch;
  if (failure.phase === "finalization") return t.failureFinalize;
  return t.failureExecution;
}
