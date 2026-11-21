import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { localBackendOrigin, validateLiveRunId } from "../apiClient";
import type { Language } from "../i18n";
import type { RunProjection } from "../runProjection";
import { workspaceCopy } from "../workspaceCopy";
import { trackTone, type WorkspaceStatus } from "../workspaceStatus";
import { shortFailureDescription } from "./workspaceRunDetails";

type WorkspaceTaskTrackProps = {
  language: Language;
  phase: WorkspaceStatus | "idle";
  title: string;
  run?: RunProjection;
  baseUrl?: string;
  acknowledged: boolean;
  startedAt?: number;
  endedAt?: number;
  action?: ReactNode;
};

const trackCopy = {
  zh: {
    steps: ["受理", "排队", "研究", "读取", "就绪"],
    waiting: "自动更新，无需操作", confirmation: "请先检查提交结果。", retry: "可重新读取。",
    edit: "可编辑后再提交。", failed: "停止", blocked: "受阻", review: "复核", pending: "待交付",
    elapsed: (seconds: number) => seconds < 60 ? `已用 ${seconds} 秒`
      : `已用 ${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`,
    latestSearch: "最近完成搜索"
  },
  en: {
    steps: ["Received", "Queued", "Research", "Read", "Ready"],
    waiting: "No action needed.", confirmation: "Check the submission result.", retry: "You can retry the read.",
    edit: "Edit and submit again.", failed: "Stopped", blocked: "Blocked", review: "Review", pending: "Delivery",
    elapsed: (seconds: number) => seconds < 60 ? `Elapsed ${seconds}s`
      : `Elapsed ${Math.floor(seconds / 60)}m ${seconds % 60}s`,
    latestSearch: "Last completed search"
  }
};

type TrackCopy = (typeof trackCopy)[Language];
const WAITING = new Set<WorkspaceTaskTrackProps["phase"]>(["submitting", "received", "lookup", "queued", "running", "reading"]);

function currentStep(phase: WorkspaceTaskTrackProps["phase"], run: RunProjection | undefined, labels: TrackCopy) {
  switch (phase) {
    case "queued": return { index: 1 };
    case "running": return { index: 2 };
    case "reading":
    case "readInterrupted": return { index: 3 };
    case "delivered": return { index: 4 };
    case "blocked": return { index: 3, label: labels.blocked };
    case "review": return { index: 3, label: labels.review };
    case "pendingDelivery": return { index: 3, label: labels.pending };
    case "failed": {
      const failure = run?.failureCause;
      const stopPhase = failure?.kind === "observed" ? failure.phase : undefined;
      const executedSegment = run?.segments.some(({ status }) =>
        status === "running" || status === "completed" || status === "completed_with_fallback");
      const index = stopPhase === "dispatch" ? 1 : stopPhase === "finalization" ? 3
        : stopPhase === "execution" || executedSegment ? 2 : 0;
      return { index, label: labels.failed };
    }
    case "observeInterrupted":
    case "lookup":
      if (run?.execution_status === "running") return { index: 2 };
      if (run?.execution_status === "pending") return { index: 1 };
      return { index: 0 };
    default: return { index: 0 };
  }
}

const SCOPED_SEARCH_TOOLS = new Set(["tavily_search", "tavily_search_dedup"]);
const TELEMETRY_SCHEMA = "dra.telemetry-record.v1";
const TELEMETRY_CAP = 500;
const ACTIVITY_INTERVAL_MS = 8_000;
const ISO_TIMESTAMP = /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/u;

function latestSearch(value: unknown, runId: string, threadId: string, segmentId: string) {
  if (!Array.isArray(value) || value.length > TELEMETRY_CAP) return undefined;
  let latest: number | undefined;
  for (const entry of value) {
    if (!entry || typeof entry !== "object" || Array.isArray(entry)) continue;
    if (entry.schema !== TELEMETRY_SCHEMA || entry.run_id !== runId || entry.thread_id !== threadId ||
        entry.segment_id !== segmentId || entry.status !== "success" || !SCOPED_SEARCH_TOOLS.has(entry.tool_name) ||
        typeof entry.timestamp !== "string" || !ISO_TIMESTAMP.test(entry.timestamp)) continue;
    const timestamp = Date.parse(entry.timestamp);
    if (Number.isFinite(timestamp) && (latest === undefined || latest < timestamp)) latest = timestamp;
  }
  return latest;
}

function useLatestSearch(baseUrl: string | undefined, run: RunProjection | undefined) {
  const origin = baseUrl ? localBackendOrigin(baseUrl) : undefined;
  const runId = run?.run_id;
  const threadId = run?.thread_id;
  const segmentId = run?.segments.find(({ status }) => status === "running")?.segment_id;
  const [activity, setActivity] = useState<{
    origin: string; runId: string; threadId: string; segmentId: string; timestamp: number;
  }>();

  useEffect(() => {
    if (!origin || !runId || !validateLiveRunId(runId).ok || !threadId || !segmentId) return;
    const controller = new AbortController();
    let nextRead: number | undefined;

    async function read(origin: string, runId: string, threadId: string, segmentId: string) {
      let timestamp: number | undefined;
      try {
        const response = await fetch(`${origin}/api/telemetry/runs/${encodeURIComponent(runId)}`, {
          signal: controller.signal, redirect: "error", cache: "no-store"
        });
        if (response.ok) timestamp = latestSearch(await response.json(), runId, threadId, segmentId);
        else if (response.status === 401 || response.status === 403 || response.status === 404) {
          if (!controller.signal.aborted) setActivity(undefined);
          return;
        }
      } catch {
        // This optional local read has no effect on the task state.
      }
      if (controller.signal.aborted) return;
      setActivity(timestamp === undefined ? undefined : { origin, runId, threadId, segmentId, timestamp });
      nextRead = window.setTimeout(() => void read(origin, runId, threadId, segmentId), ACTIVITY_INTERVAL_MS);
    }

    void read(origin, runId, threadId, segmentId);
    return () => {
      controller.abort();
      window.clearTimeout(nextRead);
    };
  }, [origin, runId, threadId, segmentId]);

  return activity && activity.origin === origin && activity.runId === runId &&
    activity.threadId === threadId && activity.segmentId === segmentId ? activity.timestamp : undefined;
}

function ElapsedTime({ labels, startedAt, endedAt }: { labels: TrackCopy; startedAt: number; endedAt?: number }) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (endedAt !== undefined) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [endedAt, startedAt]);

  const elapsed = Math.max(0, Math.floor(((endedAt ?? now) - startedAt) / 1_000));
  return <time className="dw-task-elapsed" dateTime={`PT${elapsed}S`}>{labels.elapsed(elapsed)}</time>;
}

export function WorkspaceTaskTrack({
  language, phase, title, run, baseUrl, acknowledged, startedAt, endedAt, action
}: WorkspaceTaskTrackProps) {
  const track = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const element = track.current;
    const workspace = element?.closest<HTMLElement>(".dra-workspace");
    if (!element || !workspace || typeof ResizeObserver === "undefined") return;
    const header = workspace.querySelector(".dw-header");
    const heights = [[element, "--dw-track-height"], [header, "--dw-header-offset"]] as const;
    const update = () => {
      for (const [target, property] of heights) {
        const height = target?.getBoundingClientRect().height;
        if (height) workspace.style.setProperty(property, `${height}px`);
      }
    };
    const observer = new ResizeObserver(update);
    for (const [target] of heights) {
      if (target) observer.observe(target);
    }
    update();
    return () => {
      observer.disconnect();
      for (const [, property] of heights) workspace.style.removeProperty(property);
    };
  }, []);

  const labels = trackCopy[language];
  const t = workspaceCopy[language];
  const tone = phase === "blocked" ? "red" : trackTone(phase);
  const glyph = tone === "green" ? "✓" : tone === "red" ? "×" : tone === "idle" ? "–"
    : tone === "amber" ? "!" : "·";
  const status = phase === "failed" ? shortFailureDescription(language, run?.failureCause) ?? t.statuses.failed
    : phase === "idle" ? t.currentIdle : t.statuses[phase];
  const waiting = WAITING.has(phase);
  const hint = waiting ? labels.waiting : phase === "ambiguous" ? labels.confirmation
    : phase === "observeInterrupted" || phase === "readInterrupted" ? labels.retry
    : phase === "rejected" ? labels.edit : undefined;
  const activity = useLatestSearch(baseUrl, phase === "running" ? run : undefined);
  const step = currentStep(phase, run, labels);
  const position = { "--dw-task-position": `${step.index * 25}%` } as CSSProperties;
  const moving = phase === "received" || phase === "queued" || phase === "running" || phase === "reading";
  const showProgress = acknowledged && phase !== "idle";

  return <div className="dw-status dw-task-track" data-tone={tone} data-phase={phase} ref={track}>
    <div className="dw-chrome dw-task-track-header">
      <span className="dw-stage">
        <span className="dw-stage-icon" aria-hidden="true">{glyph}</span>
        <span role="status" aria-atomic="true">{status}</span>
      </span>
      {title && <span className="dw-track-title" title={title}>{title}</span>}
      {(startedAt !== undefined || hint) && <div className="dw-task-meta">
        {startedAt !== undefined && <ElapsedTime labels={labels} startedAt={startedAt} endedAt={endedAt} />}
        {hint && <span>{hint}</span>}
      </div>}
      {action}
    </div>
    {showProgress && <div className="dw-task-journey" style={position} data-moving={moving}>
      <div className="dw-task-rail" aria-hidden="true">
        <span className="dw-task-fill"><span className="dw-task-pin" /></span>
      </div>
      <ol className="dw-task-steps" aria-label={t.progress} role="list">
        {labels.steps.map((label, index) => <li key={label}
          aria-current={index === step.index ? "step" : undefined}>
          {index === step.index ? step.label ?? label : label}
        </li>)}
      </ol>
    </div>}
    {activity !== undefined && <p className="dw-task-activity">
      {labels.latestSearch} <time dateTime={new Date(activity).toISOString()}>
        {new Intl.DateTimeFormat(language === "zh" ? "zh-CN" : "en", {
          hour: "numeric", minute: "2-digit", second: "2-digit"
        }).format(activity)}
      </time>
    </p>}
  </div>;
}
