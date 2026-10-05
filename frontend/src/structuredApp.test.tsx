import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
    expect(screen.getAllByRole("button", { name: "下载报告" }).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "English" }));
    expect(screen.getByRole("heading", { name: "Source-bound candidate findings" })).toBeInTheDocument();
    expect(screen.getByText("Binding locates the candidate in an observed source snippet. It does not prove source truth or claim entailment; Evidence verification remains service-owned.")).toBeInTheDocument();
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
