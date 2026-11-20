import type { LiveRunState } from "./useLiveRun";
import type { workspaceCopy } from "./workspaceCopy";

export type WorkspaceStatus = keyof typeof workspaceCopy.zh.statuses;

export function workspaceStatus(state: LiveRunState, requestedRunId?: string, submitted = false): WorkspaceStatus {
  const { status, run } = state;
  switch (status) {
    case "idle":
    case "checking":
      return "connecting";
    case "ready":
      return "ready";
    case "creating":
      return "submitting";
    case "reconciliation_required":
      return "ambiguous";
    case "error":
      if (!state.created && !requestedRunId && !run) return submitted || state.health || state.findings ? "rejected" : "offline";
      if (!run && !state.created && state.error?.retryable === false) return "lookupFailed";
      return run?.delivery_status === "ready" ? "readInterrupted" : "observeInterrupted";
    case "observation_interrupted":
      return run?.delivery_status === "ready" ? "readInterrupted" : "observeInterrupted";
    case "result":
      return "delivered";
    case "terminal":
      if (run?.execution_status === "failed") return "failed";
      if (run?.delivery_status === "review_required") return "review";
      if (run?.delivery_status === "blocked") return "blocked";
      return "pendingDelivery";
    case "polling":
      if (!run) return state.created ? "received" : "lookup";
      if (run.execution_status === "running") return "running";
      if (run.execution_status === "pending") return "queued";
      return run.delivery_status === "ready" ? "reading" : "lookup";
    default:
      return "offline";
  }
}

export function statusTone(status: WorkspaceStatus) {
  switch (status) {
    case "delivered":
      return "success";
    case "offline":
    case "lookupFailed":
    case "ambiguous":
    case "rejected":
    case "observeInterrupted":
    case "readInterrupted":
    case "blocked":
    case "failed":
      return "error";
    case "ready":
      return "idle";
    default:
      return "running";
  }
}

export function trackTone(status: WorkspaceStatus | "idle") {
  switch (status) {
    case "idle":
    case "connecting":
    case "ready":
    case "offline":
      return "idle";
    case "running":
    case "lookup":
    case "reading":
      return "blue";
    case "delivered":
      return "green";
    case "failed":
      return "red";
    default:
      return "amber";
  }
}
