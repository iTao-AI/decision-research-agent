import { act, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { parseRunProjection } from "../runProjection";
import { WorkspaceTaskTrack } from "./workspaceTaskTrack";

const RUN = {
  run_id: "run_track", thread_id: "thread_track", profile_id: "generic-evidence-report",
  execution_status: "running", delivery_status: "pending", review_status: "not_required", state_version: 1,
  segments: [], evidence: [], review_workflow: null, review_decision: null, review_resolution: null
};
const TRACK = { language: "en" as const, title: "Python 3.13 support" };

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("WorkspaceTaskTrack", () => {
  it("reveals the progress line only once a request has been accepted", () => {
    const { rerender } = render(<WorkspaceTaskTrack {...TRACK} phase="idle" acknowledged={false} />);
    expect(screen.queryByRole("list", { name: "Research progress" })).not.toBeInTheDocument();

    rerender(<WorkspaceTaskTrack {...TRACK} phase="ambiguous" acknowledged={false}
      action={<button type="button">Check submission result</button>} />);
    expect(screen.getByRole("button", { name: "Check submission result" })).toBeVisible();
    expect(screen.getByText("Check the submission result.")).toBeVisible();
    expect(screen.queryByRole("list", { name: "Research progress" })).not.toBeInTheDocument();

    rerender(<WorkspaceTaskTrack {...TRACK} phase="received" acknowledged />);
    const track = screen.getByRole("list", { name: "Research progress" });
    expect(within(track).getByText("Received")).toHaveAttribute("aria-current", "step");
    expect(screen.getByText("No action needed.")).toBeVisible();
    expect(screen.queryByText(/latest search/i)).not.toBeInTheDocument();
  });

  it("shows the observed blocked step without marking an unread report as read", () => {
    const running = parseRunProjection(RUN);
    const { rerender } = render(<WorkspaceTaskTrack {...TRACK} phase="running" acknowledged run={running} />);
    expect(screen.getByText("Research")).toHaveAttribute("aria-current", "step");

    const blocked = parseRunProjection({ ...RUN, execution_status: "completed", delivery_status: "blocked" });
    rerender(<WorkspaceTaskTrack {...TRACK} phase="blocked" acknowledged run={blocked}
      action={<button type="button">View delivery details</button>} />);
    expect(screen.getByRole("status")).toHaveTextContent("Delivery blocked");
    expect(screen.getByText("Blocked")).toHaveAttribute("aria-current", "step");
    expect(screen.queryByText("Read")).not.toBeInTheDocument();
    expect(screen.getByText("Ready")).not.toHaveAttribute("aria-current");
  });

  it("updates real elapsed time for the observed task and freezes it at the terminal time", () => {
    vi.useFakeTimers();
    vi.setSystemTime(5_000);
    const running = parseRunProjection(RUN);
    const { rerender } = render(<WorkspaceTaskTrack {...TRACK} phase="running" acknowledged run={running} startedAt={2_000} />);
    expect(screen.getByText("Elapsed 3s")).toBeVisible();
    act(() => vi.advanceTimersByTime(2_000));
    expect(screen.getByText("Elapsed 5s")).toBeVisible();

    const ready = parseRunProjection({ ...RUN, execution_status: "completed", delivery_status: "ready" });
    rerender(<WorkspaceTaskTrack {...TRACK} phase="delivered" acknowledged run={ready} startedAt={2_000} endedAt={7_000} />);
    act(() => vi.advanceTimersByTime(5_000));
    expect(screen.getByText("Elapsed 5s")).toBeVisible();
    expect(screen.getByText("Ready")).toHaveAttribute("aria-current", "step");
  });
  it("reports the most recent successful search only for the current running segment", async () => {
    const run = parseRunProjection({
      ...RUN, segments: [{ segment_id: "active_segment", kind: "initial", sequence: 0, attempt: 1, status: "running" }]
    });
    const event = {
      schema: "dra.telemetry-record.v1", run_id: run.run_id, thread_id: run.thread_id,
      segment_id: "active_segment", status: "success", timestamp: "2026-11-21T01:51:03.703369+00:00",
      tool_name: "tavily_search", args: "must stay out of the interface"
    };
    const later = { ...event, timestamp: "2026-11-21T01:51:06.099151+00:00" };
    const ineligible = { ...event, timestamp: "2026-11-21T01:51:07.099151+00:00" };
    const fetch = vi.fn(async () => Response.json([
      later, event,
      { ...ineligible, run_id: "different_run" },
      { ...ineligible, thread_id: "different_thread" },
      { ...ineligible, segment_id: "previous_segment" },
      { ...ineligible, status: "SUCCESS" },
      { ...ineligible, tool_name: "unknown_tool" },
      { ...ineligible, tool_name: "TAVILY_SEARCH" },
      { ...ineligible, timestamp: "2026-11-21" }
    ]));
    vi.stubGlobal("fetch", fetch);
    const { rerender } = render(<WorkspaceTaskTrack {...TRACK} phase="running" acknowledged run={run}
      baseUrl="http://127.0.0.1:8000" />);
    const activity = await screen.findByText("Last completed search");
    expect(activity.querySelector("time")).toHaveAttribute("dateTime", "2026-11-21T01:51:06.099Z");
    expect(fetch).toHaveBeenCalledWith("http://127.0.0.1:8000/api/telemetry/runs/run_track", expect.any(Object));
    expect(screen.queryByText(/must stay out|tavily_search/)).not.toBeInTheDocument();

    rerender(<WorkspaceTaskTrack {...TRACK} phase="blocked" acknowledged run={run}
      baseUrl="http://127.0.0.1:8000" />);
    expect(screen.queryByText("Last completed search")).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledOnce();
  });

  it("suppresses optional activity if the service does not permit the read", async () => {
    const run = parseRunProjection({
      ...RUN, segments: [{ segment_id: "active_segment", kind: "initial", sequence: 0, attempt: 1, status: "running" }]
    });
    const fetch = vi.fn(async () => Response.json({}, { status: 403 }));
    vi.stubGlobal("fetch", fetch);
    render(<WorkspaceTaskTrack {...TRACK} phase="running" acknowledged run={run}
      baseUrl="http://127.0.0.1:8000" />);
    await act(async () => {});
    expect(fetch).toHaveBeenCalledOnce();
    expect(screen.queryByText("Last completed search")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Research in progress");
  });

});
