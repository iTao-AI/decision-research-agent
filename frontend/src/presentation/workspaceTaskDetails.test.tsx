import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { parseRunProjection } from "../runProjection";
import type { LiveRunState } from "../useLiveRun";
import { shortFailureDescription, WorkspaceRetainedEvidence } from "./workspaceRunDetails";
import { WorkspaceTaskDetails } from "./workspaceTaskDetails";

const LIVE: LiveRunState = { baseUrl: "http://127.0.0.1:8000", mode: "live", status: "polling" };
const RUN = {
  run_id: "run_observed", thread_id: "thread_observed", profile_id: "generic",
  execution_status: "failed", review_status: "not_required", delivery_status: "failed", state_version: 2,
  segments: [], evidence: [], review_workflow: null, review_decision: null, review_resolution: null,
  failure_cause: {
    schema_version: "dra.run-failure-cause.v1", observation_status: "observed", phase: "finalization",
    code: "run_timeout", recorded_at: "2026-11-20T02:30:00Z"
  }
};
const SOURCE = {
  evidence_id: "ev_1", source_url: "https://example.com/observed", source_identity: "example.com/observed",
  evidence_fingerprint: "sha256:abc", citation_status: "uncited", verification_status: "unverified"
};

describe("WorkspaceTaskDetails", () => {
  it("updates observed progress without claiming acceptance before a receipt exists", () => {
    const { rerender } = render(<WorkspaceTaskDetails language="en" phase="submitting"
      state={{ ...LIVE, status: "creating" }} />);
    expect(screen.queryByText("Request received")).not.toBeInTheDocument();

    rerender(<WorkspaceTaskDetails language="en" phase="running" runId="run_observed"
      state={{
        ...LIVE, created: { run_id: "run_observed", segment_id: "seg_1", thread_id: "thread_observed",
          status: "started", idempotent_replay: false },
        run: parseRunProjection({ ...RUN, execution_status: "running", delivery_status: "pending", failure_cause: null })
      }}
      questions={[{ question_id: "q1", text: "What did the source observe?" },
        { question_id: "q2", text: "What is still unknown?" }]} />);

    expect(screen.getByText("Request received")).toBeVisible();
    expect(screen.getByText("Research in progress")).toBeVisible();
    expect(screen.getByText("What did the source observe?")).toBeVisible();
    expect(screen.getByText("What is still unknown?")).toBeVisible();
  });

  it("shows the observed stop phase, cause, and retained source before the new draft action", () => {
    const run = parseRunProjection({
      ...RUN, evidence: [{ ...SOURCE, snippet: "<img src=x> This was retained exactly." }]
    });
    const onOpenDraft = vi.fn();
    const { container } = render(<WorkspaceTaskDetails language="en" phase="failed" runId={run.run_id}
      state={{ ...LIVE, status: "terminal", run }} onOpenDraft={onOpenDraft}
      questions={[{ question_id: "q1", text: "What did the source observe?" }]} />);

    expect(screen.getByText("Finalization")).toBeVisible();
    expect(screen.getByText("Research timed out during finalization")).toBeVisible();
    expect(shortFailureDescription("en", run.failureCause)).toBe("Finalization timed out");
    expect(screen.getByText("run_timeout")).toBeVisible();
    const source = screen.getByRole("link", { name: "example.com/observed" });
    expect(source).toHaveAttribute("href", "https://example.com/observed");
    expect(screen.getByText("<img src=x> This was retained exactly.")).toBeVisible();
    expect(container.querySelector("img")).toBeNull();
    const action = screen.getByRole("button", { name: "Edit questions for new research" });
    expect(source.compareDocumentPosition(action) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    fireEvent.click(action);
    expect(onOpenDraft).toHaveBeenCalledOnce();
  });

  it("keeps a historical failed run readable without inventing a cause or source", () => {
    const run = parseRunProjection({ ...RUN, failure_cause: {
      schema_version: "dra.run-failure-cause.v1", observation_status: "not_observed"
    } });
    render(<WorkspaceTaskDetails language="en" phase="failed" state={{ ...LIVE, status: "terminal", run }} />);

    expect(screen.getByText("The service provided no failure reason.")).toBeVisible();
    expect(screen.getByText("The current record lists no retained sources.")).toBeVisible();
    expect(screen.queryByText("Finalization")).not.toBeInTheDocument();
    expect(shortFailureDescription("en", run.failureCause)).toBeUndefined();
  });

  it("shows a delivery gate separately from execution failure and rechecks the loaded run", () => {
    const run = parseRunProjection({
      ...RUN, execution_status: "completed", review_status: "required", delivery_status: "review_required",
      failure_cause: null
    });
    const onCheckStatus = vi.fn();
    render(<WorkspaceTaskDetails language="en" phase="review" runId={run.run_id}
      state={{ ...LIVE, status: "terminal", run }} onCheckStatus={onCheckStatus} />);

    const delivery = within(screen.getByRole("region", { name: "Awaiting review" }));
    expect(delivery.getByText("completed")).toBeVisible();
    expect(delivery.getByText("review_required")).toBeVisible();
    expect(screen.queryByText("The service provided no failure reason.")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Check status" }));
    expect(onCheckStatus).toHaveBeenCalledOnce();
  });

  it("keeps a retained source recognizable when its projection has no displayable snippet or link", () => {
    const run = parseRunProjection({
      ...RUN, evidence: [{ ...SOURCE, source_url: "javascript:alert(1)" }]
    });
    render(<WorkspaceRetainedEvidence language="en" run={run} />);

    expect(screen.getByText("example.com/observed")).toBeVisible();
    expect(screen.getByText("No retained snippet is available to display.")).toBeVisible();
    expect(screen.queryByRole("link", { name: "example.com/observed" })).not.toBeInTheDocument();
  });
});
