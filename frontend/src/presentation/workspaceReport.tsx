import type { Ref } from "react";
import { copy, type Language } from "../i18n";
import type { ResearchFindingsResponse } from "../researchFindings";
import type { RunProjection, RunResultResponse } from "../runProjection";
import { ResearchFindingsReader, type UnresolvedQuestionControls, type WorkspaceReportView } from "./researchFindingsReader";
import { downloadArtifact, SafeMarkdownDocument } from "./resultReader";

export function WorkspaceReport({ language, result, findings, followUp, reportRef, initialView, onFollowQuestion, run }: {
  language: Language;
  result: RunResultResponse;
  findings?: ResearchFindingsResponse;
  followUp?: UnresolvedQuestionControls;
  reportRef?: Ref<HTMLElement>;
  initialView?: WorkspaceReportView;
  onFollowQuestion?: (questionId: string, trigger: HTMLElement) => void;
  run?: RunProjection;
}) {
  const t = copy[language].reader;
  const artifact = result.artifact;
  const boundFindings = findings?.run_id === result.run_id ? findings : undefined;
  return <article className="dw-report" aria-label={t.title} tabIndex={-1} ref={reportRef}>
    {boundFindings
      ? <ResearchFindingsReader language={language} findings={boundFindings} followUp={followUp} variant="workspace"
        initialView={initialView} onFollowQuestion={onFollowQuestion} evidence={run?.run_id === result.run_id ? run.evidence : undefined} />
      : <SafeMarkdownDocument content={artifact.content} />}
    <div className="dw-report-actions" key={`${result.run_id}/${artifact.content_hash}`}>
      <details className="dw-details dw-report-raw">
        <summary>{language === "zh" ? "查看报告原稿" : "View original report"}</summary>
        <button type="button" onClick={() => downloadArtifact(artifact.content, artifact.artifact_id)}>
          {language === "zh" ? "下载 Markdown" : "Download Markdown"}
        </button>
        <pre>{artifact.content}</pre>
      </details>
    </div>
  </article>;
}
