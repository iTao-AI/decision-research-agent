import { useState } from "react";
import { validateLiveRunId } from "../apiClient";
import type { Language } from "../i18n";
import { workspaceCopy } from "../workspaceCopy";

const REPORT_PARAMETER = "report";

export function requestedReportId() {
  const runId = new URL(window.location.href).searchParams.get(REPORT_PARAMETER);
  return runId && validateLiveRunId(runId).ok ? runId : undefined;
}

export function reportAddress(runId?: string) {
  const url = new URL(window.location.href);
  if (runId) url.searchParams.set(REPORT_PARAMETER, runId);
  else url.searchParams.delete(REPORT_PARAMETER);
  return url;
}

export function WorkspaceReportLink({ language, runId }: { language: Language; runId: string }) {
  const t = workspaceCopy[language];
  const [copyState, setCopyState] = useState<"idle" | "copied" | "manual">("idle");
  const url = new URL(window.location.pathname, window.location.origin);
  url.searchParams.set(REPORT_PARAMETER, runId);
  const address = url.href;
  return <div className="dw-share-link">
    <button type="button" className="dw-outline" onClick={async () => {
      try {
        await navigator.clipboard.writeText(address);
        setCopyState("copied");
      } catch {
        setCopyState("manual");
      }
    }}>{t.copyReport}</button>
    <span className="dw-share-feedback" aria-live="polite">{copyState === "copied" ? t.copied : ""}</span>
    {copyState === "manual" && <input aria-label={t.reportLink} value={address} readOnly
      ref={(input) => { input?.focus(); input?.select(); }} />}
  </div>;
}
