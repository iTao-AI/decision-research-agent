import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { buildLiveConsoleProjection } from "../consoleProjection";
import type { HealthResponse } from "../apiClient";
import type { RunProjection } from "../runProjection";
import { LiveEvidenceSourcePanel } from "./evidenceSourcePanel";

const HEALTH: HealthResponse = {
  service: "decision-research-agent",
  status: "ok"
};

describe("LiveEvidenceSourcePanel", () => {
  it("renders observed source identity and blocks unsafe URLs", () => {
    const projection = buildLiveConsoleProjection({
      health: HEALTH,
      created: undefined,
      run: unsafeSourceRun(),
      result: undefined,
      status: "terminal"
    });

    const { container } = render(<LiveEvidenceSourcePanel language="zh" projection={projection} />);

    expect(screen.getAllByText("Untrusted source").length).toBeGreaterThan(1);
    expect(screen.getByText("该 URL 未通过 HTTP(S) 安全检查")).toBeInTheDocument();
    expect(container.querySelector(".source-detail a")).not.toBeInTheDocument();
    expect(screen.getByText("当前运行没有观察到可展示的 excerpt；不会从报告正文推断。")).toBeInTheDocument();
    expect(container.querySelector("script")).not.toBeInTheDocument();
  });

  it("reselects a current source when the observed Evidence collection changes", async () => {
    const user = userEvent.setup();
    const firstRun = buildLiveConsoleProjection({
      health: HEALTH,
      created: undefined,
      run: sourceRun("run_live_sources_v1", [
        sourceEvidence("ev_live_first", "First source"),
        sourceEvidence("ev_live_second", "Second source")
      ]),
      result: undefined,
      status: "terminal"
    });
    const { rerender } = render(<LiveEvidenceSourcePanel language="zh" projection={firstRun} />);

    await user.click(screen.getByRole("button", { name: /Second source/ }));
    expect(screen.getByRole("heading", { name: "Second source" })).toBeInTheDocument();

    const replacementRun = buildLiveConsoleProjection({
      health: HEALTH,
      created: undefined,
      run: sourceRun("run_live_sources_v2", [sourceEvidence("ev_live_replacement", "Replacement source")]),
      result: undefined,
      status: "terminal"
    });
    rerender(<LiveEvidenceSourcePanel language="zh" projection={replacementRun} />);

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Replacement source" })).toBeInTheDocument();
    });
    expect(screen.queryByText("ev_live_second")).not.toBeInTheDocument();
    expect(screen.getAllByText("ev_live_replacement").length).toBeGreaterThan(0);
  });
});

function unsafeSourceRun(): RunProjection {
  return {
    run_id: "run_live_unsafe_source",
    thread_id: "thread_live_unsafe_source",
    profile_id: "generic",
    execution_status: "completed",
    review_status: "not_required",
    delivery_status: "ready",
    state_version: 1,
    segments: [],
    evidence: [
      {
        evidence_id: "ev_unsafe_source",
        source_url: "javascript:alert(1)",
        source_identity: "Untrusted source",
        evidence_fingerprint: "sha256:unsafe-source",
        citation_status: "cited",
        verification_status: "unverified"
      }
    ],
    review: {
      workflow: null,
      decision: null,
      resolution: null
    },
    failureCause: { kind: "not_applicable" }
  };
}

function sourceRun(runId: string, evidence: RunProjection["evidence"]): RunProjection {
  return {
    ...unsafeSourceRun(),
    run_id: runId,
    thread_id: `${runId}_thread`,
    evidence
  };
}

function sourceEvidence(evidenceId: string, sourceIdentity: string) {
  return {
    evidence_id: evidenceId,
    source_url: `https://example.com/${evidenceId}`,
    source_identity: sourceIdentity,
    evidence_fingerprint: `sha256:${evidenceId}`,
    citation_status: "cited" as const,
    verification_status: "verified"
  };
}
