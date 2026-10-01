import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { findingsResponse, markdownResult, structuredRun } from "./test/researchFindingsFixture";

afterEach(() => vi.unstubAllGlobals());

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
