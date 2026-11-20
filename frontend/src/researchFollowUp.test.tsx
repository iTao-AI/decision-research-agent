import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { findingsResponse, markdownResult, structuredRun } from "./test/researchFindingsFixture";
import { openExistingResearch, useEnglish } from "./test/researchWorkspaceInteractions";

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

function fixture({ lostNew = false, rejectNew = false, noUnresolved = false, invalid = false, blocked = false,
  beforeAcknowledgement = Promise.resolve()
} = {}) {
  const posts: Post[] = [];
  let newScope = [{ question_id: "q1", text: "New question" }];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (init?.method === "POST") {
      const entry = { body: String(init.body), key: new Headers(init.headers).get("Idempotency-Key") };
      posts.push(entry);
      const body = JSON.parse(entry.body);
      newScope = body.scope.questions ?? newScope;
      await beforeAcknowledgement;
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

async function openKnownFollowUp(user: ReturnType<typeof userEvent.setup>, language: "zh" | "en" = "zh") {
  const known = within(screen.getByRole("region", { name: language === "zh" ? "已有研究" : "Existing research" }));
  await user.click(await known.findByRole("button", {
    name: language === "zh" ? "跟进未解问题" : "Follow up on open questions"
  }));
}

async function closeToHome(user: ReturnType<typeof userEvent.setup>) {
  const nestedBack = screen.queryByRole("button", { name: "返回上一层" });
  if (nestedBack) await user.click(nestedBack);
  await user.click(screen.getByRole("button", { name: "返回首页" }));
}

async function openOriginal({ genericForm = false, english = false } = {}) {
  let identity = 0;
  const user = userEvent.setup();
  render(<StrictMode><App liveOptions={{ randomUUID: () => `new-${++identity}`, pollIntervalMs: 1 }} /></StrictMode>);
  await screen.findByRole("button", { name: "服务已连接，打开连接设置" });
  if (genericForm) await user.selectOptions(screen.getByRole("combobox", { name: "研究模式" }), "generic");
  await user.type(screen.getByRole("textbox", { name: "研究问题" }), "My existing ordinary draft");
  if (english) await useEnglish(user);
  await openExistingResearch(user, "run_original", english ? "en" : "zh");
  await openKnownFollowUp(user, english ? "en" : "zh");
  return user;
}

async function prepare(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("checkbox", { name: "选择未解决问题 2" }));
  await user.click(screen.getByRole("button", { name: "准备新研究草稿" }));
  return within(screen.getByRole("region", { name: "新研究草稿" }));
}

describe("unresolved report to independent editable research draft", () => {
  it("copies only selected question text, preserves the original report and home draft and makes no preparation POST", async () => {
    const posts = fixture();
    const user = await openOriginal();
    expect(screen.queryByRole("checkbox", { name: "选择未解决问题 1" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "准备新研究草稿" })).toBeDisabled();
    const draft = await prepare(user);
    expect(draft.getByRole("textbox", { name: "新研究问题 1" })).toHaveValue("Unknown 中文😀");
    expect(draft.getByText("run_original")).toBeInTheDocument();
    expect(draft.getByText("More evidence needed")).toBeInTheDocument();
    expect(draft.getAllByRole("textbox")).toHaveLength(1);
    expect(posts).toHaveLength(0);
    expect(draft.getByRole("textbox", { name: "新研究问题 1" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "返回上一层" }));
    await user.click(screen.getByRole("button", { name: "阅读这份报告" }));
    expect(screen.getByRole("button", { name: "下载 Markdown" })).toBeEnabled();
    expect(screen.getByRole("region", { name: "Answered question" })).toBeVisible();
    await closeToHome(user);
    expect(screen.getByRole("textbox", { name: "研究问题" })).toHaveValue("My existing ordinary draft");
  });

  it("manually creates an edited structured scope with a fresh identity even from the generic ordinary form", async () => {
    const posts = fixture();
    const user = await openOriginal({ genericForm: true });
    const draft = await prepare(user);
    fireEvent.change(draft.getByRole("textbox", { name: "新研究问题 1" }), { target: { value: "More specific new question" } });
    expect(posts).toHaveLength(0);
    const confirm = draft.getByRole("button", { name: "确认并运行新研究" });
    fireEvent.click(confirm); fireEvent.click(confirm);
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(JSON.parse(posts[0].body)).toEqual({ query: "More specific new question", thread_id: "demo-console-new-1",
      profile_id: "generic-evidence-report", scope: { questions: [{ question_id: "q1", text: "More specific new question" }] } });
    expect(posts[0].key).toBe("run-create-console-new-1");
    const readNew = await screen.findByRole("button", { name: "阅读报告" });
    expect(screen.getByRole("status")).toHaveTextContent("报告已就绪");
    expect(screen.getByText("这份续研草稿已提交。可从顶部任务栏查看它的进展。")).toBeVisible();
    expect(draft.getByText("run_original")).toBeVisible();
    expect(draft.getByRole("textbox", { name: "新研究问题 1" })).toBeDisabled();
    await closeToHome(user);
    expect(screen.getByRole("textbox", { name: "研究问题" })).toHaveValue("My existing ordinary draft");
    await user.click(readNew);
    expect(screen.getByRole("region", { name: "More specific new question" })).toBeVisible();
    await closeToHome(user);
    await user.click(screen.getByRole("button", { name: "新建研究" }));
    expect(screen.getByRole("combobox", { name: "研究模式" })).toHaveValue("generic");
    expect(screen.getByRole("textbox", { name: "研究问题" })).toHaveValue("My existing ordinary draft");
  });

  it("requires explicit replacement after edits and cancels without overwriting the ordinary editor", async () => {
    const posts = fixture();
    const user = await openOriginal();
    const draft = await prepare(user);
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
    await closeToHome(user);
    expect(screen.getByRole("textbox", { name: "研究问题" })).toHaveValue("My existing ordinary draft");
    expect(posts).toHaveLength(0);
  });

  it("uses existing blank/byte/count validation and scope controls in the independent editor", async () => {
    const posts = fixture();
    const user = await openOriginal();
    const draft = await prepare(user);
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

  it("clears selections and the draft when a different known report is opened", async () => {
    const posts = fixture();
    const user = await openOriginal();
    await prepare(user);

    await openExistingResearch(user, "run_other");
    await openKnownFollowUp(user);
    expect(screen.getByRole("checkbox", { name: "选择未解决问题 2" })).not.toBeChecked();
    expect(screen.queryByRole("region", { name: "新研究草稿" })).not.toBeInTheDocument();
    expect(posts).toHaveLength(0);
  });

  it("clears the known draft on a service change and preserves the home input", async () => {
    const posts = fixture();
    const user = await openOriginal();
    await prepare(user);

    await user.click(screen.getByRole("button", { name: "服务已连接，打开连接设置" }));
    const settings = within(screen.getByRole("dialog", { name: "连接设置" }));
    const url = settings.getByRole("textbox", { name: "本地后端地址" });
    await user.clear(url);
    await user.type(url, "http://127.0.0.1:9000");
    await user.click(settings.getByRole("button", { name: "保存连接" }));
    await screen.findByRole("button", { name: "服务已连接，打开连接设置" });
    expect(screen.queryByRole("region", { name: "新研究草稿" })).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "研究问题" })).toHaveValue("My existing ordinary draft");
    expect(posts).toHaveLength(0);
  });

  it("reconciles the frozen follow-up through the task bar after returning home", async () => {
    const posts = fixture({ lostNew: true });
    const user = await openOriginal();
    const draft = await prepare(user);
    fireEvent.change(draft.getByRole("textbox", { name: "新研究问题 1" }), { target: { value: "Frozen new scope" } });
    await user.click(draft.getByRole("button", { name: "确认并运行新研究" }));
    const checkReceipt = await screen.findByRole("button", { name: "核对同一请求" });
    expect(draft.getByRole("textbox", { name: "新研究问题 1" })).toHaveValue("Frozen new scope");
    expect(draft.getByRole("textbox", { name: "新研究问题 1" })).toBeDisabled();
    expect(draft.getByRole("button", { name: "取消新研究草稿" })).toBeDisabled();
    expect(posts).toHaveLength(1);
    await closeToHome(user);
    expect(screen.getByRole("textbox", { name: "研究问题" })).toHaveValue("My existing ordinary draft");
    expect(screen.getByRole("button", { name: "已提交" })).toHaveAttribute("aria-disabled", "true");
    await user.click(checkReceipt);
    await user.click(within(screen.getByRole("region", { name: "提交回执待确认" }))
      .getByRole("button", { name: "重试同一请求" }));
    await screen.findByRole("button", { name: "阅读报告" });
    expect(posts[1]).toEqual(posts[0]);
    expect(posts).toHaveLength(2);
    expect(JSON.parse(posts[0].body).scope.questions).toEqual([{ question_id: "q1", text: "Frozen new scope" }]);
  });

  it("delivers a follow-up through the task bar when acknowledgement arrives after returning home", async () => {
    let acknowledge: () => void = () => {};
    const beforeAcknowledgement = new Promise<void>((resolve) => { acknowledge = resolve; });
    const posts = fixture({ beforeAcknowledgement });
    const user = await openOriginal();
    const draft = await prepare(user);
    await user.click(draft.getByRole("button", { name: "确认并运行新研究" }));
    expect(screen.getByRole("status")).toHaveTextContent("正在提交");
    await closeToHome(user);
    expect(screen.getByRole("textbox", { name: "研究问题" })).toHaveValue("My existing ordinary draft");

    await act(async () => { acknowledge(); });
    const readReport = await screen.findByRole("button", { name: "阅读报告" });
    const fetch = vi.mocked(globalThis.fetch);
    const requestCount = fetch.mock.calls.length;
    await user.click(readReport);
    expect(screen.getByRole("region", { name: "Unknown 中文😀" })).toBeVisible();
    expect(fetch).toHaveBeenCalledTimes(requestCount);
    expect(posts).toHaveLength(1);
  });

  it("returns from the task bar to the edited continuation after a rejection arrives with the pane closed", async () => {
    let acknowledge: () => void = () => {};
    const beforeAcknowledgement = new Promise<void>((resolve) => { acknowledge = resolve; });
    const posts = fixture({ rejectNew: true, beforeAcknowledgement });
    const user = await openOriginal();
    const draft = await prepare(user);
    fireEvent.change(draft.getByRole("textbox", { name: "新研究问题 1" }), {
      target: { value: "Keep my edited continuation" }
    });
    await user.click(draft.getByRole("button", { name: "确认并运行新研究" }));
    await closeToHome(user);

    await act(async () => { acknowledge(); });
    await user.click(await screen.findByRole("button", { name: "编辑问题" }));
    const recovered = within(screen.getByRole("region", { name: "新研究草稿" }));
    expect(recovered.getByRole("textbox", { name: "新研究问题 1" })).toHaveValue("Keep my edited continuation");
    expect(recovered.getByRole("button", { name: "确认并运行新研究" })).toBeEnabled();
    expect(posts).toHaveLength(1);
  });

  it("keeps only the edited draft after a definite rejection and creates a fresh intent on submit", async () => {
    const posts = fixture({ rejectNew: true });
    const user = await openOriginal({ genericForm: true });
    const draft = await prepare(user);
    fireEvent.change(draft.getByRole("textbox", { name: "新研究问题 1" }), { target: { value: "Recover edited question one" } });
    await user.click(draft.getByRole("button", { name: "新增问题" }));
    fireEvent.change(draft.getByRole("textbox", { name: "新研究问题 2" }), { target: { value: "Recover edited question two" } });
    await user.click(draft.getByRole("button", { name: "确认并运行新研究" }));
    await screen.findByText("提交未成功");
    expect(draft.getByRole("textbox", { name: "新研究问题 1" })).toHaveValue("Recover edited question one");
    expect(draft.getByRole("textbox", { name: "新研究问题 2" })).toHaveValue("Recover edited question two");
    expect(screen.queryByRole("button", { name: "重试同一请求" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "来源绑定的候选结论" })).not.toBeInTheDocument();
    expect(posts).toHaveLength(1);

    fireEvent.change(draft.getByRole("textbox", { name: "新研究问题 2" }), { target: { value: "Revised recovered second question" } });
    await user.click(draft.getByRole("button", { name: "确认并运行新研究" }));
    await screen.findByRole("button", { name: "阅读报告" });
    expect(posts).toHaveLength(2);
    expect(posts[1].key).not.toBe(posts[0].key);
    expect(JSON.parse(posts[1].body)).toEqual({
      query: "Recover edited question one", thread_id: "demo-console-new-2",
      profile_id: "generic-evidence-report", scope: { questions: [
        { question_id: "q1", text: "Recover edited question one" },
        { question_id: "q2", text: "Revised recovered second question" }
      ] }
    });
    expect(draft.getByRole("button", { name: "确认并运行新研究" })).toBeDisabled();
    await closeToHome(user);
    expect(screen.getByRole("textbox", { name: "研究问题" })).toHaveValue("My existing ordinary draft");
  });

  it("returns keyboard focus to a source checkbox when cancelling with no questions selected", async () => {
    const posts = fixture();
    const user = await openOriginal();
    const draft = await prepare(user);
    const checkbox = screen.getByRole("checkbox", { name: "选择未解决问题 2" });
    await user.click(checkbox);
    expect(screen.getByRole("button", { name: "准备新研究草稿" })).toBeDisabled();
    draft.getByRole("button", { name: "取消新研究草稿" }).focus();
    await user.keyboard("{Enter}");
    expect(checkbox).toHaveFocus();
    expect(screen.queryByRole("region", { name: "新研究草稿" })).not.toBeInTheDocument();
    expect(posts).toHaveLength(0);
  });

  it("clears the source draft when another known report cannot be read", async () => {
    const posts = fixture();
    const user = await openOriginal();
    await prepare(user);
    const ordinaryFetch = globalThis.fetch;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/run_bad")) return Promise.resolve(Response.json(structuredRun("run_bad")));
      if (url.endsWith("/run_bad/findings")) return Promise.resolve(Response.json({
        code: "run_result_unavailable", problem: "Unavailable", cause: "Fixture", fix: "Inspect run", retryable: false
      }, { status: 409 }));
      return ordinaryFetch(input, init);
    }));

    await openExistingResearch(user, "run_bad");
    await screen.findByText("报告读取中断");
    await user.click(screen.getByText("运行详情", { selector: "summary" }));
    expect(screen.getByText("run_result_unavailable")).toBeVisible();
    expect(within(screen.getByRole("region", { name: "已有研究" })).getAllByText("run_bad")[0]).toBeVisible();
    expect(screen.queryByRole("region", { name: "新研究草稿" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "下载 Markdown" })).not.toBeInTheDocument();
    expect(screen.queryByText("研究失败")).not.toBeInTheDocument();
    expect(posts).toHaveLength(0);

    await closeToHome(user);
    expect(screen.getByRole("textbox", { name: "研究问题" })).toHaveValue("My existing ordinary draft");
  });

  it("ignores stale findings after opening another run and preserves its edited draft", async () => {
    const posts = fixture();
    const user = await openOriginal();
    await prepare(user);
    const ordinaryFetch = globalThis.fetch;
    let release!: (value: Response) => void;
    let signal: AbortSignal | null | undefined;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/run_late")) return Promise.resolve(Response.json(structuredRun("run_late")));
      if (url.endsWith("/run_late/findings")) {
        signal = init?.signal;
        return new Promise<Response>((resolve) => { release = resolve; });
      }
      return ordinaryFetch(input, init);
    }));

    await openExistingResearch(user, "run_late");
    await waitFor(() => expect(release).toBeTypeOf("function"));
    await openExistingResearch(user, "run_other");
    expect(signal?.aborted).toBe(true);
    await openKnownFollowUp(user);
    const draft = await prepare(user);
    fireEvent.change(draft.getByRole("textbox", { name: "新研究问题 1" }), { target: { value: "Keep newer draft" } });

    await act(async () => release(Response.json(report("run_late"))));
    expect(draft.getByRole("textbox", { name: "新研究问题 1" })).toHaveValue("Keep newer draft");
    expect(draft.getByText("run_other")).toBeVisible();
    expect(screen.queryByText("run_late")).not.toBeInTheDocument();
    expect(vi.mocked(globalThis.fetch).mock.calls.some(([input]) => String(input).endsWith("/run_late/result"))).toBe(false);
    expect(posts).toHaveLength(0);
  });

  it("supports English keyboard selection/preparation/cancellation without any creation", async () => {
    const posts = fixture();
    const user = await openOriginal({ english: true });
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

  it.each([
    ["noUnresolved", "报告已就绪"], ["invalid", "报告读取中断"], ["blocked", "交付受阻"]
  ] as const)("offers no preparation action for %s reports", async (mode, status) => {
    const posts = fixture({ [mode]: true });
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("button", { name: "服务已连接，打开连接设置" });
    await openExistingResearch(user, "run_original");
    const known = within(screen.getByRole("region", { name: "已有研究" }));
    await known.findByRole("heading", { name: status });
    if (mode === "noUnresolved") {
      await openKnownFollowUp(user);
      expect(screen.getByText("这份报告没有可继续跟进的未解问题。")).toBeVisible();
    } else {
      expect(known.queryByRole("button", { name: "跟进未解问题" })).not.toBeInTheDocument();
    }
    expect(screen.queryByRole("button", { name: "准备新研究草稿" })).not.toBeInTheDocument();
    expect(posts).toHaveLength(0);
  });
});
