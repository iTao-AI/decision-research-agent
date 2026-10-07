import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { findingsResponse, markdownResult, structuredRun } from "./test/researchFindingsFixture";

afterEach(() => vi.unstubAllGlobals());

function captureCreates(lostFirstResponse = false) {
  const posts: { body: string; key: string | null }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (init?.method === "POST") {
      posts.push({ body: String(init.body), key: new Headers(init.headers).get("Idempotency-Key") });
      if (lostFirstResponse && posts.length === 1) throw new TypeError("lost response");
      return new Response(JSON.stringify({ run_id: "run_structured", segment_id: "segment", status: "started", thread_id: "demo-console-fixed", idempotent_replay: posts.length > 1 }));
    }
    return new Response(JSON.stringify(url.endsWith("/health") ? { service: "decision-research-agent", status: "ok" } :
      url.endsWith("/findings") ? findingsResponse() : url.endsWith("/result") ? markdownResult() : structuredRun()));
  }));
  return posts;
}

async function structuredEditor() {
  const user = userEvent.setup();
  render(<StrictMode><App liveOptions={{ randomUUID: () => "fixed", pollIntervalMs: 1 }} /></StrictMode>);
  await user.click(screen.getByRole("button", { name: "真实后端" }));
  await user.click(screen.getByRole("button", { name: "检查后端" }));
  await user.selectOptions(screen.getByRole("combobox", { name: "研究模式" }), "generic-evidence-report");
  return user;
}

describe("multi-question creation editor", () => {
  it("submits five explicit questions and blocks blank rows and a sixth addition", async () => {
    const posts = captureCreates();
    const user = await structuredEditor();
    fireEvent.change(screen.getByRole("textbox", { name: "研究问题" }), { target: { value: "  One😀\n  " } });
    for (const [index, text] of ["Two", "Three", "Four", "Five"].entries()) {
      await user.click(screen.getByRole("button", { name: "新增问题" }));
      expect(screen.getByRole("button", { name: "运行并获取结果" })).toBeDisabled();
      fireEvent.change(screen.getByRole("textbox", { name: `研究问题 ${index + 2}` }), { target: { value: text } });
    }
    expect(screen.getByRole("button", { name: "新增问题" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "运行并获取结果" }));
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

  it("keeps surviving IDs after editing, middle/first removal and re-adding", async () => {
    const posts = captureCreates(); const user = await structuredEditor();
    fireEvent.change(screen.getByRole("textbox", { name: "研究问题" }), { target: { value: "One" } });
    await user.click(screen.getByRole("button", { name: "新增问题" }));
    fireEvent.change(screen.getByRole("textbox", { name: "研究问题 2" }), { target: { value: "Two" } });
    await user.click(screen.getByRole("button", { name: "新增问题" }));
    fireEvent.change(screen.getByRole("textbox", { name: "研究问题 3" }), { target: { value: "Three" } });
    await user.click(screen.getByRole("button", { name: "删除问题 2" }));
    expect(screen.getByRole("textbox", { name: "研究问题 2" })).toHaveValue("Three");
    fireEvent.change(screen.getByRole("textbox", { name: "研究问题 2" }), { target: { value: "Edited third" } });
    await user.click(screen.getByRole("button", { name: "删除问题 1" }));
    expect(screen.getByRole("textbox", { name: "研究问题" })).toHaveValue("Edited third");
    await user.click(screen.getByRole("button", { name: "新增问题" }));
    fireEvent.change(screen.getByRole("textbox", { name: "研究问题 2" }), { target: { value: "Fourth" } });
    await user.click(screen.getByRole("button", { name: "运行并获取结果" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(JSON.parse(posts[0].body)).toMatchObject({ query: "Edited third", scope: { questions: [
      { question_id: "q3", text: "Edited third" }, { question_id: "q4", text: "Fourth" }
    ] } });
  });

  it("locks the full editor until the exact complete lost-response request is reconciled", async () => {
    const posts = captureCreates(true); const user = await structuredEditor();
    await user.click(screen.getByRole("button", { name: "新增问题" }));
    fireEvent.change(screen.getByRole("textbox", { name: "研究问题 2" }), { target: { value: "Second" } });
    await user.click(screen.getByRole("button", { name: "运行并获取结果" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "重试同一请求" })).toBeInTheDocument());
    expect(screen.getByRole("textbox", { name: "研究问题" })).toBeDisabled();
    expect(screen.getByRole("textbox", { name: "研究问题 2" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "新增问题" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "删除问题 1" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "删除问题 2" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "重试同一请求" }));
    await waitFor(() => expect(posts).toHaveLength(2));
    expect(posts[1]).toEqual(posts[0]);
    expect(JSON.parse(posts[0].body).scope.questions).toHaveLength(2);
  });

  it("supports English keyboard addition/removal and prevents an empty scope", async () => {
    captureCreates(); const user = await structuredEditor();
    await user.click(screen.getByRole("button", { name: "English" }));
    expect(screen.getByRole("button", { name: "Remove question 1" })).toBeDisabled();
    screen.getByRole("button", { name: "Add question" }).focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("textbox", { name: "Research question 2" })).toHaveFocus();
    screen.getByRole("button", { name: "Remove question 2" }).focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("textbox", { name: "Research question" })).toHaveFocus();
  });
});

describe("explicit structured console", () => {
  it("keeps generic default, selects opt-in structured profile and displays accepted questions and candidates", async () => {
    const requests: { url: string; body?: string }[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input); requests.push({ url, body: init?.body ? String(init.body) : undefined });
      const value = url.endsWith("/health") ? { service: "decision-research-agent", status: "ok" } :
        init?.method === "POST" ? { run_id: "run_structured", segment_id: "segment", status: "started", thread_id: "demo-console-fixed", idempotent_replay: false } :
        url.endsWith("/findings") ? findingsResponse() : url.endsWith("/result") ? markdownResult() : structuredRun();
      return new Response(JSON.stringify(value));
    }));
    const user = userEvent.setup();
    render(<App liveOptions={{ randomUUID: () => "fixed", pollIntervalMs: 1 }} />);
    await user.click(screen.getByRole("button", { name: "真实后端" }));
    expect(screen.getByRole("combobox", { name: "研究模式" })).toHaveValue("generic");
    await user.click(screen.getByRole("button", { name: "检查后端" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "研究模式" }), "generic-evidence-report");
    fireEvent.change(screen.getByRole("textbox", { name: "研究问题" }), { target: { value: "  原始问题\n😀  " } });
    await user.click(screen.getByRole("button", { name: "运行并获取结果" }));
    await waitFor(() => expect(screen.getByRole("heading", { name: "来源绑定的候选结论" })).toBeInTheDocument());
    expect(JSON.parse(requests.find((request) => request.body)?.body ?? "null")).toMatchObject({
      profile_id: "generic-evidence-report", query: "  原始问题\n😀  ", scope: { questions: [{ question_id: "q1", text: "  原始问题\n😀  " }] }
    });
    expect(screen.getByText("证据不足")).toBeInTheDocument();
    expect(screen.getByText("两个来源的更新时间存在矛盾")).toBeInTheDocument();
    expect(screen.getByText("片段绑定不证明结论真实")).toBeInTheDocument();
    const directory = screen.getByRole("navigation", { name: "问题目录" });
    expect(within(directory).getAllByRole("button")).toHaveLength(2);
    expect(directory).not.toHaveTextContent("原始问题");
    fireEvent.change(screen.getByRole("textbox", { name: "研究问题" }), { target: { value: "New editable draft" } });
    expect(directory).not.toHaveTextContent("New editable draft");
    await user.click(within(directory).getByRole("button", { name: /未解决问题/ }));
    expect(within(screen.getByRole("region", { name: "未解决问题" })).getByText("证据不足")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "下载报告" }).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "English" }));
    expect(screen.getByRole("heading", { name: "Source-bound candidate findings" })).toBeInTheDocument();
    expect(screen.getByText("Binding locates the candidate in an observed source snippet. It does not prove source truth or claim entailment; Evidence verification remains service-owned.")).toBeInTheDocument();
    expect(within(screen.getByRole("navigation", { name: "Question directory" })).getByRole("button", { name: /未解决问题/ })).toHaveAttribute("aria-current", "location");
    await user.click(screen.getByRole("tab", { name: "Raw" }));
    expect(screen.getByRole("tabpanel").textContent).toBe("# Canonical report");
  });

  it("clears reader selection and opened source when attaching another run or switching profile", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/health")) return new Response(JSON.stringify({ service: "decision-research-agent", status: "ok" }));
      const runId = url.includes("run_next") ? "run_next" : "run_first";
      const value = findingsResponse(runId);
      value.report.questions[0].text = `${runId} accepted question`;
      value.report.findings[0].statement = `${runId} observed candidate`;
      value.artifact.content = JSON.stringify(value.report);
      return new Response(JSON.stringify(url.endsWith("/findings") ? value : url.endsWith("/result") ? markdownResult(runId) : structuredRun(runId)));
    }));
    const user = userEvent.setup(); render(<StrictMode><App /></StrictMode>);
    await user.click(screen.getByRole("button", { name: "真实后端" }));
    await user.click(screen.getByRole("button", { name: "检查后端" }));
    const runField = screen.getByRole("textbox", { name: "已知 run_id" });
    await user.type(runField, "run_first");
    await user.click(screen.getByRole("button", { name: "观察已知运行" }));
    await waitFor(() => expect(screen.getByRole("region", { name: "run_first accepted question" })).toBeInTheDocument());
    await user.click(within(screen.getByRole("navigation", { name: "问题目录" })).getAllByRole("button")[0]);
    await user.click(screen.getByRole("button", { name: "查看完整持久化片段" }));
    expect(screen.getByRole("region", { name: "完整持久化片段" })).toBeInTheDocument();
    await user.clear(runField); await user.type(runField, "run_next");
    await user.click(screen.getByRole("button", { name: "观察已知运行" }));
    await waitFor(() => expect(screen.getByRole("region", { name: "run_next accepted question" })).toBeInTheDocument());
    expect(screen.queryByRole("region", { name: "run_first accepted question" })).not.toBeInTheDocument();
    expect(screen.queryByText("run_first observed candidate")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "完整持久化片段" })).not.toBeInTheDocument();
    expect(within(screen.getByRole("navigation", { name: "问题目录" })).getAllByRole("button").every((button) => !button.hasAttribute("aria-current"))).toBe(true);
    await user.selectOptions(screen.getByRole("combobox", { name: "研究模式" }), "generic-evidence-report");
    expect(screen.queryByRole("navigation", { name: "问题目录" })).not.toBeInTheDocument();
    expect(screen.queryByText("run_next observed candidate")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "下载报告" })).not.toBeInTheDocument();
  });

  it("keeps an all-unresolved zero-findings run blocked without fabricating question regions from the draft", async () => {
    const urls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input); urls.push(url);
      return new Response(JSON.stringify(url.endsWith("/health") ? { service: "decision-research-agent", status: "ok" } :
        { ...structuredRun("all_unresolved", "blocked"), findings_issues: ["empty_research_output"],
          findings_outcome: { requested_question_count: 5, covered_question_count: 0, unresolved_question_count: 5, reference_binding_failure_count: 0 } }));
    }));
    const user = await structuredEditor();
    fireEvent.change(screen.getByRole("textbox", { name: "研究问题" }), { target: { value: "Unaccepted editable draft" } });
    await user.type(screen.getByRole("textbox", { name: "已知 run_id" }), "all_unresolved");
    await user.click(screen.getByRole("button", { name: "观察已知运行" }));
    await waitFor(() => expect(screen.getByText("empty_research_output")).toBeInTheDocument());
    expect(screen.queryByRole("navigation", { name: "问题目录" })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Unaccepted editable draft" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "下载报告" })).not.toBeInTheDocument();
    expect(urls.some((url) => /\/(result|findings)$/.test(url))).toBe(false);
  });

  it("shows service blocked reasons without findings or report download", async () => {
    const urls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input); urls.push(url);
      return new Response(JSON.stringify(url.endsWith("/health") ? { service: "decision-research-agent", status: "ok" } :
        { ...structuredRun("blocked", "blocked"), findings_issues: ["excerpt_not_found"],
          findings_outcome: { requested_question_count: 1, covered_question_count: 0, unresolved_question_count: 1, reference_binding_failure_count: 1 } }));
    }));
    const user = userEvent.setup(); render(<App />);
    await user.click(screen.getByRole("button", { name: "真实后端" }));
    await user.click(screen.getByRole("button", { name: "检查后端" }));
    await user.type(screen.getByRole("textbox", { name: "已知 run_id" }), "blocked");
    await user.click(screen.getByRole("button", { name: "观察已知运行" }));
    await waitFor(() => expect(screen.getByText("excerpt_not_found")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "下载报告" })).not.toBeInTheDocument();
    expect(urls.some((url) => /\/(result|findings)$/.test(url))).toBe(false);
  });
});
