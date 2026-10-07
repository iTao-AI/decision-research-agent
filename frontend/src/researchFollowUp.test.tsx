import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { findingsResponse, markdownResult, structuredRun } from "./test/researchFindingsFixture";

afterEach(() => vi.unstubAllGlobals());
const originalQuestions = [
  { question_id: "old_answered", text: "Answered question" },
  { question_id: "old_unknown", text: "Unknown 中文😀" },
  { question_id: "old_other", text: "Other unresolved question" }
];
type Post = { body: string; key: string | null };

function report(runId: string, questions = originalQuestions, unresolved = true) {
  const value = findingsResponse(runId);
  value.report.questions = questions;
  value.report.findings[0].question_id = questions[0].question_id;
  value.report.dispositions = questions.map((q, index) => index > 0 && unresolved
    ? { question_id: q.question_id, status: "unresolved", reason: "More evidence needed" }
    : { question_id: q.question_id, status: "candidate_findings" });
  if (!unresolved) value.report.findings = questions.map((q, i) => ({
    ...value.report.findings[0], finding_id: `f${i + 1}`, question_id: q.question_id
  }));
  value.artifact.content = JSON.stringify(value.report);
  return value;
}

function fixture({ lostNew = false, rejectNew = false, noUnresolved = false, invalid = false, blocked = false } = {}) {
  const posts: Post[] = [];
  let newScope = [{ question_id: "q1", text: "New question" }];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (init?.method === "POST") {
      const entry = { body: String(init.body), key: new Headers(init.headers).get("Idempotency-Key") };
      posts.push(entry);
      const body = JSON.parse(entry.body);
      newScope = body.scope.questions ?? newScope;
      if (lostNew && posts.length === 1) throw new TypeError("lost response");
      if (rejectNew && posts.length === 1) return new Response(JSON.stringify({ code: "service_unavailable",
        problem: "Unavailable", cause: "Fixture", fix: "Check backend", retryable: false }), { status: 503 });
      return new Response(JSON.stringify({ run_id: "run_new", segment_id: "segment_new", status: "started",
        thread_id: body.thread_id, idempotent_replay: lostNew && posts.length > 1 }));
    }
    if (url.endsWith("/health")) return new Response(JSON.stringify({ service: "decision-research-agent", status: "ok" }));
    const runId = url.includes("/run_new") ? "run_new" : url.includes("/run_other") ? "run_other" : "run_original";
    const value = url.endsWith("/findings") ? invalid ? { report: "invalid" } : report(runId, runId === "run_new" ? newScope : originalQuestions, !noUnresolved)
      : url.endsWith("/result") ? markdownResult(runId)
      : blocked ? { ...structuredRun(runId, "blocked"), findings_issues: ["empty_research_output"] } : structuredRun(runId);
    return new Response(JSON.stringify(value));
  }));
  return posts;
}

async function openOriginal({ genericForm = false, english = false } = {}) {
  let identity = 0;
  const user = userEvent.setup();
  render(<StrictMode><App liveOptions={{ randomUUID: () => `new-${++identity}`, pollIntervalMs: 1 }} /></StrictMode>);
  await user.click(screen.getByRole("button", { name: "真实后端" }));
  await user.click(screen.getByRole("button", { name: "检查后端" }));
  if (!genericForm) await user.selectOptions(screen.getByRole("combobox", { name: "研究模式" }), "generic-evidence-report");
  fireEvent.change(screen.getByRole("textbox", { name: "研究问题" }), { target: { value: "My existing ordinary draft" } });
  await user.type(screen.getByRole("textbox", { name: "已知 run_id" }), "run_original");
  await user.click(screen.getByRole("button", { name: "观察已知运行" }));
  await waitFor(() => expect(screen.getByRole("navigation", { name: "问题目录" })).toBeInTheDocument());
  if (english) await user.click(screen.getByRole("button", { name: "English" }));
  return user;
}

async function prepare(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("checkbox", { name: "选择未解决问题 2" }));
  await user.click(screen.getByRole("button", { name: "准备新研究草稿" }));
  return within(screen.getByRole("region", { name: "新研究草稿" }));
}

describe("unresolved report to independent editable research draft", () => {
  it("copies only selected question text, preserves ordinary edits/report/download and makes no preparation POST", async () => {
    const posts = fixture(); const user = await openOriginal();
    expect(screen.queryByRole("checkbox", { name: "选择未解决问题 1" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "准备新研究草稿" })).toBeDisabled();
    const draft = await prepare(user);
    expect(draft.getByRole("textbox", { name: "新研究问题 1" })).toHaveValue("Unknown 中文😀");
    expect(draft.getByText("run_original")).toBeInTheDocument();
    expect(draft.getByText("More evidence needed")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "研究问题" })).toHaveValue("My existing ordinary draft");
    expect(screen.getByRole("button", { name: "下载报告" })).toBeEnabled();
    expect(posts).toHaveLength(0);
    expect(draft.getByRole("textbox", { name: "新研究问题 1" })).toHaveFocus();
    const ids = [...document.querySelectorAll("textarea[id]")].map((element) => element.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("manually creates an edited structured scope with a fresh identity even from the generic ordinary form", async () => {
    const posts = fixture(); const user = await openOriginal({ genericForm: true });
    const draft = await prepare(user);
    fireEvent.change(draft.getByRole("textbox", { name: "新研究问题 1" }), { target: { value: "More specific new question" } });
    expect(posts).toHaveLength(0);
    const confirm = draft.getByRole("button", { name: "确认并运行新研究" });
    fireEvent.click(confirm); fireEvent.click(confirm);
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(JSON.parse(posts[0].body)).toEqual({ query: "More specific new question", thread_id: "demo-console-new-1",
      profile_id: "generic-evidence-report", scope: { questions: [{ question_id: "q1", text: "More specific new question" }] } });
    expect(posts[0].key).toBe("run-create-console-new-1");
    await waitFor(() => expect(screen.getByRole("region", { name: "More specific new question" })).toBeInTheDocument());
    expect(screen.queryByRole("region", { name: "新研究草稿" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "研究模式" })).toHaveValue("generic");
  });

  it("requires explicit replacement after edits and cancels without overwriting the ordinary editor", async () => {
    const posts = fixture(); const user = await openOriginal(); const draft = await prepare(user);
    fireEvent.change(draft.getByRole("textbox", { name: "新研究问题 1" }), { target: { value: "Keep my edited draft" } });
    await user.click(screen.getByRole("checkbox", { name: "选择未解决问题 3" }));
    await user.click(screen.getByRole("button", { name: "准备新研究草稿" }));
    expect(draft.getByRole("textbox", { name: "新研究问题 1" })).toHaveValue("Keep my edited draft");
    expect(draft.getByRole("button", { name: "确认并运行新研究" })).toBeDisabled();
    await user.click(draft.getByRole("button", { name: "保留当前草稿" }));
    expect(draft.getByRole("textbox", { name: "新研究问题 1" })).toHaveValue("Keep my edited draft");
    expect(draft.getByRole("textbox", { name: "新研究问题 1" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "准备新研究草稿" }));
    await user.click(draft.getByRole("button", { name: "替换当前草稿" }));
    expect(draft.getAllByRole("textbox")).toHaveLength(2);
    expect(draft.getByRole("textbox", { name: "新研究问题 1" })).toHaveValue("Unknown 中文😀");
    await user.click(draft.getByRole("button", { name: "取消新研究草稿" }));
    expect(screen.queryByRole("region", { name: "新研究草稿" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "准备新研究草稿" })).toHaveFocus();
    expect(screen.getByRole("textbox", { name: "研究问题" })).toHaveValue("My existing ordinary draft");
    expect(posts).toHaveLength(0);
  });

  it("uses existing blank/byte/count validation and scope controls in the independent editor", async () => {
    const posts = fixture(); const user = await openOriginal(); const draft = await prepare(user);
    const first = draft.getByRole("textbox", { name: "新研究问题 1" });
    fireEvent.change(first, { target: { value: " " } });
    expect(draft.getByRole("button", { name: "确认并运行新研究" })).toBeDisabled();
    fireEvent.change(first, { target: { value: "汉".repeat(1366) } });
    expect(first).toHaveAttribute("aria-invalid", "true");
    expect(draft.getByRole("button", { name: "确认并运行新研究" })).toBeDisabled();
    fireEvent.change(first, { target: { value: "Valid first" } });
    for (let index = 2; index <= 5; index++) {
      await user.click(draft.getByRole("button", { name: "新增问题" }));
      expect(draft.getByRole("textbox", { name: `新研究问题 ${index}` })).toHaveFocus();
      fireEvent.change(draft.getByRole("textbox", { name: `新研究问题 ${index}` }), { target: { value: `New ${index}` } });
    }
    expect(draft.getByRole("button", { name: "新增问题" })).toBeDisabled();
    await user.click(draft.getByRole("button", { name: "删除问题 2" }));
    expect(draft.getByRole("textbox", { name: "新研究问题 2" })).toHaveValue("New 3");
    expect(posts).toHaveLength(0);
    await user.click(draft.getByRole("button", { name: "新增问题" }));
    fireEvent.change(draft.getByRole("textbox", { name: "新研究问题 5" }), { target: { value: "Replacement question" } });
    await user.click(draft.getByRole("button", { name: "确认并运行新研究" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(JSON.parse(posts[0].body).scope.questions.map((question: { question_id: string }) => question.question_id))
      .toEqual(["q1", "q3", "q4", "q5", "q6"]);
  });

  it.each(["endpoint", "profile", "mode", "source"])("invalidates the old draft on %s change", async (context) => {
    const posts = fixture(); const user = await openOriginal(); await prepare(user);
    if (context === "endpoint") fireEvent.change(screen.getByRole("textbox", { name: "Backend base URL" }), { target: { value: "http://127.0.0.1:9000" } });
    if (context === "profile") await user.selectOptions(screen.getByRole("combobox", { name: "研究模式" }), "generic");
    if (context === "mode") await user.click(screen.getByRole("button", { name: "静态演示" }));
    if (context === "source") {
      fireEvent.change(screen.getByRole("textbox", { name: "已知 run_id" }), { target: { value: "run_other" } });
      await user.click(screen.getByRole("button", { name: "观察已知运行" }));
      await waitFor(() => expect(screen.getByRole("navigation", { name: "问题目录" })).toBeInTheDocument());
      expect(screen.getByRole("checkbox", { name: "选择未解决问题 2" })).not.toBeChecked();
    }
    expect(screen.queryByRole("region", { name: "新研究草稿" })).not.toBeInTheDocument();
    expect(posts).toHaveLength(0);
  });

  it("retains only the new frozen intent when its response is lost and reconciled", async () => {
    const posts = fixture({ lostNew: true }); const user = await openOriginal(); const draft = await prepare(user);
    fireEvent.change(draft.getByRole("textbox", { name: "新研究问题 1" }), { target: { value: "Frozen new scope" } });
    await user.click(draft.getByRole("button", { name: "确认并运行新研究" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "重试同一请求" })).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "准备新研究草稿" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "运行并获取结果" })).toBeDisabled();
    expect(screen.getByRole("textbox", { name: "研究问题" })).toBeDisabled();
    const pendingDraft = within(screen.getByRole("region", { name: "新研究草稿" }));
    expect(pendingDraft.getByRole("textbox", { name: "新研究问题 1" })).toHaveValue("Frozen new scope");
    expect(pendingDraft.getByRole("textbox", { name: "新研究问题 1" })).toBeDisabled();
    expect(pendingDraft.getByRole("button", { name: "取消新研究草稿" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "重试同一请求" }));
    await waitFor(() => expect(posts).toHaveLength(2));
    expect(posts[1]).toEqual(posts[0]);
    expect(JSON.parse(posts[0].body).scope.questions).toEqual([{ question_id: "q1", text: "Frozen new scope" }]);
  });

  it("locks selection, draft editing and submission while checking and after a service error", async () => {
    const posts = fixture(); const user = await openOriginal(); const draft = await prepare(user);
    const ordinaryFetch = globalThis.fetch;
    let release!: (value: Response) => void;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => String(input).endsWith("/health")
      ? new Promise<Response>((resolve) => { release = resolve; }) : ordinaryFetch(input, init)));
    await user.click(screen.getByRole("button", { name: "检查后端" }));
    expect(screen.getByRole("checkbox", { name: "选择未解决问题 2" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "准备新研究草稿" })).toBeDisabled();
    expect(draft.getByRole("textbox", { name: "新研究问题 1" })).toBeDisabled();
    expect(draft.getByRole("button", { name: "确认并运行新研究" })).toBeDisabled();
    release(new Response(JSON.stringify({ code: "service_unavailable", problem: "Unavailable", cause: "Fixture", fix: "Check backend", retryable: false }), { status: 503 }));
    await waitFor(() => expect(screen.getByText("service_unavailable")).toBeInTheDocument());
    expect(draft.getByRole("button", { name: "确认并运行新研究" })).toBeDisabled();
    expect(posts).toHaveLength(0);
  });

  it("unlocks the same edited draft after a successful health recheck", async () => {
    const posts = fixture(); const user = await openOriginal(); const draft = await prepare(user);
    fireEvent.change(draft.getByRole("textbox", { name: "新研究问题 1" }), { target: { value: "Keep after health recheck" } });
    const ordinaryFetch = globalThis.fetch;
    let release!: (value: Response) => void;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => String(input).endsWith("/health")
      ? new Promise<Response>((resolve) => { release = resolve; }) : ordinaryFetch(input, init)));
    await user.click(screen.getByRole("button", { name: "检查后端" }));
    expect(draft.getByRole("textbox", { name: "新研究问题 1" })).toBeDisabled();
    release(new Response(JSON.stringify({ service: "decision-research-agent", status: "ok" })));
    await waitFor(() => expect(draft.getByRole("textbox", { name: "新研究问题 1" })).toBeEnabled());
    expect(draft.getByRole("textbox", { name: "新研究问题 1" })).toHaveValue("Keep after health recheck");
    expect(draft.getByRole("button", { name: "确认并运行新研究" })).toBeEnabled();
    expect(draft.getByRole("button", { name: "取消新研究草稿" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "准备新研究草稿" })).toBeEnabled();
    expect(posts).toHaveLength(0);
  });

  it("retains only draft inputs through definite create rejection and creates a fresh intent after recovery", async () => {
    const posts = fixture({ rejectNew: true }); const user = await openOriginal({ genericForm: true }); const draft = await prepare(user);
    fireEvent.change(draft.getByRole("textbox", { name: "新研究问题 1" }), { target: { value: "Recover edited question one" } });
    await user.click(draft.getByRole("button", { name: "新增问题" }));
    fireEvent.change(draft.getByRole("textbox", { name: "新研究问题 2" }), { target: { value: "Recover edited question two" } });
    await user.click(draft.getByRole("button", { name: "确认并运行新研究" }));
    await waitFor(() => expect(screen.getByText("service_unavailable")).toBeInTheDocument());
    const recovery = within(screen.getByRole("region", { name: "新研究草稿" }));
    expect(recovery.getByRole("textbox", { name: "新研究问题 1" })).toHaveValue("Recover edited question one");
    expect(recovery.getByRole("textbox", { name: "新研究问题 2" })).toHaveValue("Recover edited question two");
    expect(recovery.getByRole("button", { name: "确认并运行新研究" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "重试同一请求" })).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "问题目录" })).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "研究问题" })).toHaveValue("My existing ordinary draft");
    expect(posts).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "检查后端" }));
    await waitFor(() => expect(recovery.getByRole("button", { name: "确认并运行新研究" })).toBeEnabled());
    fireEvent.change(recovery.getByRole("textbox", { name: "新研究问题 2" }), { target: { value: "Revised recovered second question" } });
    expect(posts).toHaveLength(1);
    await user.click(recovery.getByRole("button", { name: "确认并运行新研究" }));
    await waitFor(() => expect(posts).toHaveLength(2));
    expect(posts[1].key).not.toBe(posts[0].key);
    expect(JSON.parse(posts[1].body)).toEqual({ query: "Recover edited question one", thread_id: "demo-console-new-2",
      profile_id: "generic-evidence-report", scope: { questions: [
        { question_id: "q1", text: "Recover edited question one" }, { question_id: "q2", text: "Revised recovered second question" }
      ] } });
    await waitFor(() => expect(screen.queryByRole("region", { name: "新研究草稿" })).not.toBeInTheDocument());
    expect(screen.getByRole("combobox", { name: "研究模式" })).toHaveValue("generic");
  });

  it("returns keyboard focus to a source checkbox when cancelling with no questions selected", async () => {
    const posts = fixture(); const user = await openOriginal(); const draft = await prepare(user);
    await user.click(screen.getByRole("checkbox", { name: "选择未解决问题 2" }));
    expect(screen.getByRole("button", { name: "准备新研究草稿" })).toBeDisabled();
    draft.getByRole("button", { name: "取消新研究草稿" }).focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("checkbox", { name: "选择未解决问题 2" })).toHaveFocus();
    expect(screen.queryByRole("region", { name: "新研究草稿" })).not.toBeInTheDocument();
    expect(posts).toHaveLength(0);
  });

  it.each(["endpoint", "profile", "mode", "source"])("expires a rejected-creation draft on %s change", async (context) => {
    const posts = fixture({ rejectNew: true }); const user = await openOriginal(); const draft = await prepare(user);
    fireEvent.change(draft.getByRole("textbox", { name: "新研究问题 1" }), { target: { value: "Discard this old context edit" } });
    await user.click(draft.getByRole("button", { name: "确认并运行新研究" }));
    await waitFor(() => expect(screen.getByText("service_unavailable")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "检查后端" }));
    await waitFor(() => expect(draft.getByRole("button", { name: "确认并运行新研究" })).toBeEnabled());
    if (context === "endpoint") fireEvent.change(screen.getByRole("textbox", { name: "Backend base URL" }), { target: { value: "http://127.0.0.1:9000" } });
    if (context === "profile") await user.selectOptions(screen.getByRole("combobox", { name: "研究模式" }), "generic");
    if (context === "mode") await user.click(screen.getByRole("button", { name: "静态演示" }));
    if (context === "source") {
      fireEvent.change(screen.getByRole("textbox", { name: "已知 run_id" }), { target: { value: "run_other" } });
      await user.click(screen.getByRole("button", { name: "观察已知运行" }));
      await waitFor(() => expect(screen.getByRole("navigation", { name: "问题目录" })).toBeInTheDocument());
    }
    expect(screen.queryByRole("region", { name: "新研究草稿" })).not.toBeInTheDocument();
    expect(posts).toHaveLength(1);
  });

  it("returns cancellation focus to known-run input after definite creation recovery", async () => {
    const posts = fixture({ rejectNew: true }); const user = await openOriginal(); const draft = await prepare(user);
    await user.click(draft.getByRole("button", { name: "确认并运行新研究" }));
    await waitFor(() => expect(screen.getByText("service_unavailable")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "检查后端" }));
    await waitFor(() => expect(draft.getByRole("button", { name: "取消新研究草稿" })).toBeEnabled());
    draft.getByRole("button", { name: "取消新研究草稿" }).focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("textbox", { name: "已知 run_id" })).toHaveFocus();
    expect(screen.queryByRole("region", { name: "新研究草稿" })).not.toBeInTheDocument();
    expect(posts).toHaveLength(1);
  });

  it("clears the draft and follows known-run error gates when another run cannot be read", async () => {
    const posts = fixture(); const user = await openOriginal(); await prepare(user);
    const ordinaryFetch = globalThis.fetch;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/run_bad")) return Promise.resolve(new Response(JSON.stringify(structuredRun("run_bad"))));
      if (url.endsWith("/run_bad/findings")) return Promise.resolve(new Response(JSON.stringify({ code: "run_result_unavailable",
        problem: "Unavailable", cause: "Fixture", fix: "Inspect run", retryable: false }), { status: 409 }));
      return ordinaryFetch(input, init);
    }));
    fireEvent.change(screen.getByRole("textbox", { name: "已知 run_id" }), { target: { value: "run_bad" } });
    await user.click(screen.getByRole("button", { name: "观察已知运行" }));
    await waitFor(() => expect(screen.getByText("run_result_unavailable")).toBeInTheDocument());
    expect(screen.queryByRole("region", { name: "新研究草稿" })).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "研究问题" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "运行并获取结果" })).toBeDisabled();
    expect(posts).toHaveLength(0);
  });

  it("ignores an aborted late findings response without replacing the newer source's edited draft", async () => {
    const posts = fixture(); const user = await openOriginal(); await prepare(user);
    const ordinaryFetch = globalThis.fetch;
    let release!: (value: Response) => void;
    let signal: AbortSignal | null | undefined;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/run_late")) return Promise.resolve(new Response(JSON.stringify(structuredRun("run_late"))));
      if (url.endsWith("/run_late/findings")) {
        signal = init?.signal;
        return new Promise<Response>((resolve) => { release = resolve; });
      }
      return ordinaryFetch(input, init);
    }));
    fireEvent.change(screen.getByRole("textbox", { name: "已知 run_id" }), { target: { value: "run_late" } });
    await user.click(screen.getByRole("button", { name: "观察已知运行" }));
    await waitFor(() => expect(release).toBeTypeOf("function"));
    await user.selectOptions(screen.getByRole("combobox", { name: "研究模式" }), "generic");
    expect(signal?.aborted).toBe(true);
    fireEvent.change(screen.getByRole("textbox", { name: "已知 run_id" }), { target: { value: "run_other" } });
    await user.click(screen.getByRole("button", { name: "观察已知运行" }));
    await waitFor(() => expect(screen.getByRole("navigation", { name: "问题目录" })).toBeInTheDocument());
    const draft = await prepare(user);
    fireEvent.change(draft.getByRole("textbox", { name: "新研究问题 1" }), { target: { value: "Keep newer draft" } });
    release(new Response(JSON.stringify(report("run_late"))));
    await waitFor(() => expect(draft.getByRole("textbox", { name: "新研究问题 1" })).toHaveValue("Keep newer draft"));
    expect(draft.getByText("run_other")).toBeInTheDocument();
    expect(screen.queryByText("run_late")).not.toBeInTheDocument();
    expect(posts).toHaveLength(0);
  });

  it("supports English keyboard selection/preparation/cancellation without any creation", async () => {
    const posts = fixture(); const user = await openOriginal({ english: true });
    screen.getByRole("checkbox", { name: "Select unresolved question 2" }).focus();
    await user.keyboard(" ");
    screen.getByRole("button", { name: "Prepare new research draft" }).focus();
    await user.keyboard("{Enter}");
    const draft = within(screen.getByRole("region", { name: "New research draft" }));
    expect(draft.getByRole("textbox", { name: "New research question 1" })).toHaveFocus();
    draft.getByRole("button", { name: "Cancel new research draft" }).focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("button", { name: "Prepare new research draft" })).toHaveFocus();
    expect(posts).toHaveLength(0);
  });

  it.each(["noUnresolved", "invalid", "blocked"])("offers no preparation action for %s reports", async (mode) => {
    fixture({ [mode]: true });
    const user = userEvent.setup(); render(<App />);
    await user.click(screen.getByRole("button", { name: "真实后端" }));
    await user.click(screen.getByRole("button", { name: "检查后端" }));
    await user.type(screen.getByRole("textbox", { name: "已知 run_id" }), "run_original");
    await user.click(screen.getByRole("button", { name: "观察已知运行" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "观察已知运行" })).toBeEnabled());
    expect(screen.queryByRole("button", { name: "准备新研究草稿" })).not.toBeInTheDocument();
  });
});
