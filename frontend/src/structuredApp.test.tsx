import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { findingsResponse, markdownResult, structuredRun } from "./test/researchFindingsFixture";
import { openExistingResearch, useEnglish } from "./test/researchWorkspaceInteractions";

afterEach(() => vi.unstubAllGlobals());

function captureCreates({ lostFirstResponse = false, generic = false } = {}) {
  const posts: { body: string; key: string | null }[] = [];
  const requests: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(String(input)).pathname;
    requests.push(path);
    if (init?.method === "POST") {
      posts.push({ body: String(init.body), key: new Headers(init.headers).get("Idempotency-Key") });
      if (lostFirstResponse && posts.length === 1) throw new TypeError("lost response");
      return Response.json({
        run_id: "run_structured", segment_id: "segment", status: "started",
        thread_id: "demo-console-fixed", idempotent_replay: posts.length > 1
      });
    }
    if (path === "/health") return Response.json({ service: "decision-research-agent", status: "ok" });
    if (path.endsWith("/findings")) return Response.json(findingsResponse());
    if (path.endsWith("/result")) {
      const result = markdownResult();
      if (generic) result.artifact.kind = "research_report_markdown";
      return Response.json(result);
    }
    return Response.json({ ...structuredRun(), profile_id: generic ? "generic" : "generic-evidence-report" });
  }));
  return { posts, requests };
}

async function structuredEditor() {
  const user = userEvent.setup();
  render(<StrictMode><App liveOptions={{ randomUUID: () => "fixed", pollIntervalMs: 1 }} /></StrictMode>);
  await screen.findByRole("button", { name: "服务已连接，打开连接设置" });
  return user;
}

describe("multi-question creation editor", () => {
  it("submits five explicit questions and blocks blank rows and a sixth addition", async () => {
    const { posts } = captureCreates();
    const user = await structuredEditor();
    fireEvent.change(screen.getByRole("textbox", { name: "研究问题" }), { target: { value: "  One😀\n  " } });
    for (const [index, text] of ["Two", "Three", "Four", "Five"].entries()) {
      await user.click(screen.getByRole("button", { name: "＋ 添加子问题" }));
      expect(screen.getByRole("button", { name: "开始研究" })).toHaveAttribute("aria-disabled", "true");
      fireEvent.change(screen.getByRole("textbox", { name: `研究问题 ${index + 2}` }), { target: { value: text } });
    }
    expect(screen.getByRole("button", { name: "＋ 添加子问题" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "开始研究" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(JSON.parse(posts[0].body)).toEqual({
      query: "  One😀\n  ", thread_id: "demo-console-fixed", profile_id: "generic-evidence-report",
      scope: { questions: [
        { question_id: "q1", text: "  One😀\n  " }, { question_id: "q2", text: "Two" },
        { question_id: "q3", text: "Three" }, { question_id: "q4", text: "Four" },
        { question_id: "q5", text: "Five" }
      ] }
    });
  });

  it("keeps surviving IDs across home and comparison editor, including removal and re-adding", async () => {
    const { posts } = captureCreates();
    const user = await structuredEditor();
    fireEvent.change(screen.getByRole("textbox", { name: "研究问题" }), { target: { value: "One" } });
    const compare = screen.getByRole("button", { name: "多问题比较" });
    await user.click(compare);
    const editor = within(screen.getByRole("region", { name: "多问题比较" }));
    expect(editor.getByRole("textbox", { name: "研究问题" })).toHaveValue("One");
    await user.click(editor.getByRole("button", { name: "＋ 添加子问题" }));
    fireEvent.change(editor.getByRole("textbox", { name: "研究问题 2" }), { target: { value: "Two" } });
    await user.click(editor.getByRole("button", { name: "＋ 添加子问题" }));
    fireEvent.change(editor.getByRole("textbox", { name: "研究问题 3" }), { target: { value: "Three" } });
    await user.click(editor.getByRole("button", { name: "删除问题 2" }));
    expect(editor.getByRole("textbox", { name: "研究问题 2" })).toHaveValue("Three");
    fireEvent.change(editor.getByRole("textbox", { name: "研究问题 2" }), { target: { value: "Edited third" } });
    await user.click(editor.getByRole("button", { name: "删除问题 1" }));
    expect(editor.getByRole("textbox", { name: "研究问题" })).toHaveValue("Edited third");
    await user.click(editor.getByRole("button", { name: "＋ 添加子问题" }));
    fireEvent.change(editor.getByRole("textbox", { name: "研究问题 2" }), { target: { value: "Fourth" } });
    await user.click(editor.getByRole("button", { name: "返回首页" }));
    expect(compare).toHaveFocus();
    expect(screen.getByRole("textbox", { name: "研究问题 2" })).toHaveValue("Fourth");
    await user.click(screen.getByRole("button", { name: "开始研究" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(JSON.parse(posts[0].body)).toMatchObject({ query: "Edited third", scope: { questions: [
      { question_id: "q3", text: "Edited third" }, { question_id: "q4", text: "Fourth" }
    ] } });
  });

  it("replays all submitted questions and the same key after a lost response", async () => {
    const { posts } = captureCreates({ lostFirstResponse: true });
    const user = await structuredEditor();
    fireEvent.change(screen.getByRole("textbox", { name: "研究问题" }), { target: { value: "First" } });
    await user.click(screen.getByRole("button", { name: "＋ 添加子问题" }));
    fireEvent.change(screen.getByRole("textbox", { name: "研究问题 2" }), { target: { value: "Second" } });
    await user.click(screen.getByRole("button", { name: "开始研究" }));
    const check = await screen.findByRole("button", { name: "检查提交结果" });
    expect(screen.getByRole("textbox", { name: "研究问题" })).toHaveAttribute("readonly");
    expect(screen.getByRole("textbox", { name: "研究问题 2" })).toHaveValue("Second");
    expect(screen.getByRole("button", { name: "已提交" })).toHaveAttribute("aria-disabled", "true");
    await user.click(check);
    const retry = within(screen.getByRole("region", { name: "提交回执待确认" })).getByRole("button", { name: "重试同一请求" });
    expect(posts).toHaveLength(1);
    await user.click(retry);
    await screen.findByRole("button", { name: "阅读报告" });
    expect(posts).toHaveLength(2);
    expect(posts[1]).toEqual(posts[0]);
    expect(JSON.parse(posts[0].body).scope.questions).toEqual([
      { question_id: "q1", text: "First" }, { question_id: "q2", text: "Second" }
    ]);
  });

  it("supports English keyboard addition/removal and prevents an empty scope", async () => {
    captureCreates();
    const user = await structuredEditor();
    await useEnglish(user);
    expect(screen.queryByRole("button", { name: "Remove question 1" })).not.toBeInTheDocument();
    screen.getByRole("button", { name: "＋ Add question" }).focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("textbox", { name: "Research question 2" })).toHaveFocus();
    screen.getByRole("button", { name: "Remove question 2" }).focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("textbox", { name: "Research question" })).toHaveFocus();
    expect(screen.queryByRole("button", { name: "Remove question 1" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start research" })).toHaveAttribute("aria-disabled", "true");
  });

  it("keeps general research available and reads its Markdown without requesting findings", async () => {
    const { posts, requests } = captureCreates({ generic: true });
    const user = await structuredEditor();
    await user.selectOptions(screen.getByRole("combobox", { name: "研究模式" }), "generic");
    expect(screen.queryByRole("button", { name: "＋ 添加子问题" })).not.toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: "研究问题" }), "General question");
    await user.click(screen.getByRole("button", { name: "开始研究" }));
    const readReport = await screen.findByRole("button", { name: "阅读报告" });
    expect(screen.queryByRole("heading", { name: "Canonical report" })).not.toBeInTheDocument();
    await user.click(readReport);
    expect(await screen.findByRole("heading", { name: "Canonical report" })).toBeVisible();

    expect(posts).toHaveLength(1);
    expect(JSON.parse(posts[0].body)).toEqual({
      query: "General question", thread_id: "demo-console-fixed", profile_id: "generic", scope: {}
    });
    expect(requests.some((path) => path.endsWith("/findings"))).toBe(false);
  });
});

describe("structured reports in the research workspace", () => {
  it("reads only the service-accepted questions and keeps selection across language changes", async () => {
    const { posts } = captureCreates();
    const user = await structuredEditor();
    expect(screen.getByRole("combobox", { name: "研究模式" })).toHaveValue("generic-evidence-report");
    fireEvent.change(screen.getByRole("textbox", { name: "研究问题" }), { target: { value: "  原始问题\n😀  " } });
    await user.click(screen.getByRole("button", { name: "开始研究" }));
    await screen.findByRole("button", { name: "阅读报告" });
    expect(JSON.parse(posts[0].body)).toMatchObject({
      profile_id: "generic-evidence-report", query: "  原始问题\n😀  ",
      scope: { questions: [{ question_id: "q1", text: "  原始问题\n😀  " }] }
    });
    await user.click(screen.getByRole("button", { name: "阅读报告" }));
    const accepted = screen.getByRole("region", { name: "研究问题" });
    expect(within(accepted).getByText("来源绑定的候选结论")).toBeVisible();
    await user.click(screen.getByText("报告中的矛盾记录", { selector: "summary" }));
    expect(screen.getByText("两个来源的更新时间存在矛盾")).toBeVisible();
    expect(screen.getByText("片段绑定不证明结论真实")).toBeVisible();
    await user.click(screen.getByText("问题目录", { selector: "summary" }));
    const directory = within(screen.getByRole("navigation", { name: "问题目录" }));
    expect(directory.getAllByRole("button")).toHaveLength(2);
    expect(directory.queryByRole("button", { name: /原始问题/ })).not.toBeInTheDocument();
    const unresolved = screen.getByRole("region", { name: "未解决问题" });
    await user.click(directory.getByRole("button", { name: /未解决问题/ }));
    expect(unresolved).toHaveFocus();
    expect(within(unresolved).getByText("证据不足")).toBeVisible();
    expect(screen.getByText("查看报告原稿", { selector: "summary" })).toBeVisible();

    await useEnglish(user);
    expect(screen.getByRole("heading", { name: "Findings" })).toBeVisible();
    expect(screen.getByText(/Citations point to passages saved during this run/)).toBeVisible();
    expect(within(screen.getByRole("navigation", { name: "Question directory" }))
      .getByRole("button", { name: /未解决问题/ })).toHaveAttribute("aria-current", "location");
    await user.click(screen.getByText("View original report", { selector: "summary" }));
    expect(screen.getByText("# Canonical report")).toBeVisible();
  });

  it("clears question selection and an opened source when another run is opened", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/health")) return Response.json({ service: "decision-research-agent", status: "ok" });
      const runId = url.includes("run_next") ? "run_next" : "run_first";
      const value = findingsResponse(runId);
      value.report.questions[0].text = `${runId} accepted question`;
      value.report.findings[0].statement = `${runId} observed candidate`;
      value.artifact.content = JSON.stringify(value.report);
      return Response.json(url.endsWith("/findings") ? value : url.endsWith("/result") ? markdownResult(runId) : structuredRun(runId));
    }));
    const user = await structuredEditor();
    await openExistingResearch(user, "run_first");
    await user.click(await screen.findByRole("button", { name: "阅读这份报告" }));
    await screen.findByRole("region", { name: "run_first accepted question" });
    await user.click(screen.getByText("问题目录", { selector: "summary" }));
    await user.click(within(screen.getByRole("navigation", { name: "问题目录" }))
      .getByRole("button", { name: /run_first accepted question/ }));
    const citation = screen.getByRole("button", { name: "查看来源 1" });
    await user.click(citation);
    const source = screen.getByRole("complementary", { name: "绑定来源 1" });
    expect(source).toHaveFocus();
    expect(within(source).getByText("😀精确片段")).toBeVisible();
    await user.click(within(source).getByRole("button", { name: "展开已保存的摘录" }));
    expect(within(source).getByText("前😀精确片段后")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "返回引用处" }));
    expect(citation).toHaveFocus();
    await user.click(citation);
    expect(screen.getByRole("complementary", { name: "绑定来源 1" })).toBeVisible();

    await openExistingResearch(user, "run_next");
    await user.click(await screen.findByRole("button", { name: "阅读这份报告" }));
    await screen.findByRole("region", { name: "run_next accepted question" });
    expect(screen.queryByRole("region", { name: "run_first accepted question" })).not.toBeInTheDocument();
    expect(screen.queryByText("run_first observed candidate")).not.toBeInTheDocument();
    expect(screen.queryByRole("complementary", { name: "绑定来源 1" })).not.toBeInTheDocument();
    await user.click(screen.getByText("问题目录", { selector: "summary" }));
    expect(within(screen.getByRole("navigation", { name: "问题目录" }))
      .getByRole("button", { name: /run_next accepted question/ })).not.toHaveAttribute("aria-current");

    await user.click(screen.getByRole("button", { name: "返回上一层" }));
    await user.click(screen.getByRole("button", { name: "返回首页" }));
    expect(screen.getByRole("textbox", { name: "研究问题" })).toHaveValue("");
    expect(screen.queryByRole("navigation", { name: "问题目录" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "下载 Markdown" })).not.toBeInTheDocument();
  });

  it.each([
    ["all_unresolved", "empty_research_output", { requested_question_count: 5, covered_question_count: 0,
      unresolved_question_count: 5, reference_binding_failure_count: 0 }],
    ["blocked", "excerpt_not_found", { requested_question_count: 1, covered_question_count: 0,
      unresolved_question_count: 1, reference_binding_failure_count: 1 }]
  ])("shows blocked run %s only as status and service diagnostics", async (runId, issue, outcome) => {
    const urls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      urls.push(url);
      return Response.json(url.endsWith("/health") ? { service: "decision-research-agent", status: "ok" } : {
        ...structuredRun(runId, "blocked"), findings_issues: [issue], findings_outcome: outcome
      });
    }));
    const user = await structuredEditor();
    await user.type(screen.getByRole("textbox", { name: "研究问题" }), "Unaccepted editable draft");
    await openExistingResearch(user, runId);
    await screen.findByText("交付受阻");
    expect(screen.getByText(issue)).not.toBeVisible();
    await user.click(screen.getByText("运行详情", { selector: "summary" }));
    expect(screen.getByText(issue)).toBeVisible();
    expect(screen.queryByRole("navigation", { name: "问题目录" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Unaccepted editable draft" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "下载 Markdown" })).not.toBeInTheDocument();
    expect(urls.some((url) => /\/(result|findings)$/.test(url))).toBe(false);
  });
});
