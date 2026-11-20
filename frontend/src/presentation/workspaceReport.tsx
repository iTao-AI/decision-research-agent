import type { Ref } from "react";
import { copy, type Language } from "../i18n";
import type { ResearchFindingsResponse } from "../researchFindings";
import type { RunResultResponse } from "../runProjection";
import { ResearchFindingsReader, type UnresolvedQuestionControls } from "./researchFindingsReader";
import { downloadArtifact, SafeMarkdownDocument } from "./resultReader";

export function WorkspaceReport({ language, result, findings, followUp, reportRef }: {
  language: Language;
  result: RunResultResponse;
  findings?: ResearchFindingsResponse;
  followUp?: UnresolvedQuestionControls;
  reportRef?: Ref<HTMLElement>;
}) {
  const t = copy[language].reader;
  const artifact = result.artifact;
  const boundFindings = findings?.run_id === result.run_id ? findings : undefined;
  return <article className="dw-report" aria-label={t.title} tabIndex={-1} ref={reportRef}>
    {boundFindings
      ? <ResearchFindingsReader language={language} findings={boundFindings} followUp={followUp} variant="workspace" />
      : <SafeMarkdownDocument content={artifact.content} />}
    <div className="dw-report-actions" key={`${result.run_id}/${artifact.content_hash}`}>
      <button type="button" onClick={() => downloadArtifact(artifact.content, artifact.artifact_id)}>
        {language === "zh" ? "下载 Markdown" : "Download Markdown"}
      </button>
      <details className="dw-report-raw">
        <summary>{t.rawView}</summary>
        <pre>{artifact.content}</pre>
      </details>
    </div>
  </article>;
}
