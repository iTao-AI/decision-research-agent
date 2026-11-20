import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { findingsResponse, markdownResult, structuredRun } from "./test/researchFindingsFixture";

afterEach(() => vi.unstubAllGlobals());

const health = { service: "decision-research-agent", status: "ok" };
const options = { pollIntervalMs: 1, randomUUID: () => "test" };
const json = (value: unknown) => Response.json(value);

function fixture({
  loseResponse = false,
  resultUnavailable = false,
  delivery = "ready",
  failure = false
} = {}) {
  const requests: { method: string; path: string; body: string; key: string | null }[] = [];
  let posts = 0;
  let reads = 0;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(String(input)).pathname;
    const method = init?.method ?? "GET";
    requests.push({ path, method, body: String(init?.body ?? ""), key: new Headers(init?.headers).get("Idempotency-Key") });
    if (path === "/health") return json(health);
    if (method === "POST") {
      posts += 1;
      if (loseResponse && posts === 1) throw new TypeError("transport disconnected");
      return json({ run_id: "run_structured", segment_id: "segment", status: "started", thread_id: "demo-console-test", idempotent_replay: posts > 1 });
    }
    if (path.endsWith("/findings")) return json(findingsResponse());
    if (path.endsWith("/result")) {
      if (resultUnavailable && ++reads === 1) return new Response("{}", { status: 503 });
      return json(markdownResult());
    }
    return json(failure ? {
      ...structuredRun("run_structured", "failed"), execution_status: "failed",
      failure_cause: { schema_version: "dra.run-failure-cause.v1", observation_status: "observed", phase: "execution", code: "run_timeout", recorded_at: "2026-11-20T12:00:00Z" }
    } : structuredRun("run_structured", delivery));
  }));
  return requests;
}

async function openWorkspace() {
  render(<StrictMode><App liveOptions={options} /></StrictMode>);
  await screen.findByText("服务已连接");
}

async function submit(user: ReturnType<typeof userEvent.setup>) {
  fireEvent.change(screen.getByRole("textbox", { name: "研究问题" }), { target: { value: "  用户自己的问题\n🧭  " } });
  await user.click(screen.getByRole("button", { name: "开始研究" }));
}

describe("question-first research workspace", () => {
  it("opens a blank evidence draft and performs exactly one read-only health check, even under StrictMode", async () => {
    const requests = fixture();
    await openWorkspace();
    expect(screen.getByRole("textbox", { name: "研究问题" })).toHaveValue("");
    expect(screen.getByRole("combobox", { name: "研究模式" })).toHaveValue("generic-evidence-report");
    expect(screen.getByRole("button", { name: "开始研究" })).toHaveAttribute("aria-disabled", "true");
    expect(screen.queryByText("报告暂不可用")).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "运行编号" })).not.toBeInTheDocument();
    expect(requests.map(({ method, path }) => [method, path])).toEqual([["GET", "/health"]]);
  });

  it("keeps editing available offline and reconnects through a validated settings address", async () => {
    const fetch = vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).startsWith("http://127.0.0.1:8000/")) throw new TypeError("offline");
      return json(health);
    });
    vi.stubGlobal("fetch", fetch);
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("服务未连接");
    const question = screen.getByRole("textbox", { name: "研究问题" });
    await user.type(question, "Draft while disconnected");
    expect(screen.getByRole("button", { name: "开始研究" })).toHaveAttribute("aria-disabled", "true");

    await user.click(screen.getByRole("button", { name: "修改连接" }));
    const address = screen.getByRole("textbox", { name: "本地后端地址" });
    const save = screen.getByRole("button", { name: "保存连接" });
    fireEvent.change(address, { target: { value: "https://external.example" } });
    expect(address).toBeInvalid();
    expect(save).toBeDisabled();
    expect(fetch).toHaveBeenCalledTimes(1);
    fireEvent.change(address, { target: { value: "http://127.0.0.1:8087/" } });
    await user.click(save);
    await screen.findByText("服务已连接");
    expect(question).toHaveValue("Draft while disconnected");
    expect(screen.getByRole("button", { name: "开始研究" })).toHaveAttribute("aria-disabled", "false");
    expect(fetch.mock.calls.map(([url]) => String(url))).toEqual([
      "http://127.0.0.1:8000/health", "http://127.0.0.1:8087/health"
    ]);
  });

  it("preserves the draft and focus when cancelling an invalid independent lookup", async () => {
    const requests = fixture();
    const user = userEvent.setup();
    await openWorkspace();
    const question = screen.getByRole("textbox", { name: "研究问题" });
    await user.type(question, "My draft");
    const lookup = screen.getByRole("button", { name: "查找研究" });
    await user.click(lookup);
    const dialog = screen.getByRole("dialog", { name: "查找研究" });
    const input = within(dialog).getByRole("textbox", { name: "运行编号" });
    await user.type(input, "../invalid");
    expect(input).toBeInvalid();
    expect(within(dialog).getByRole("button", { name: "打开研究" })).toBeDisabled();
    await user.keyboard("{Escape}");
    expect(lookup).toHaveFocus();
    expect(question).toHaveValue("My draft");
    expect(screen.getByRole("button", { name: "开始研究" })).toHaveAttribute("aria-disabled", "false");
    expect(requests).toHaveLength(1);
  });

  it("creates only after submit and reads back the structured report", async () => {
    const requests = fixture();
    const user = userEvent.setup();
    await openWorkspace();
    await submit(user);
    await user.click(await screen.findByRole("button", { name: "阅读报告" }));
    expect(screen.getByRole("heading", { name: "来源绑定的候选结论" })).toBeInTheDocument();
    const post = requests.filter((request) => request.method === "POST");
    expect(post).toHaveLength(1);
    expect(JSON.parse(post[0].body)).toMatchObject({
      profile_id: "generic-evidence-report", query: "  用户自己的问题\n🧭  ",
      scope: { questions: [{ question_id: "q1", text: "  用户自己的问题\n🧭  " }] }
    });
  });

  it("admits one simultaneous submission and restores the observed live task after a read-only lookup", async () => {
    const writes: string[] = [];
    let acknowledge: (response: Response) => void = () => {};
    const acknowledgement = new Promise<Response>((resolve) => { acknowledge = resolve; });
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input)).pathname;
      if (path === "/health") return json(health);
      if (init?.method === "POST") {
        writes.push(String(init.body));
        return acknowledgement;
      }
      if (path === "/api/runs/run_structured") {
        return json({ ...structuredRun("run_structured", "pending"), execution_status: "running" });
      }
      if (path.endsWith("/findings")) return json(findingsResponse("run_other"));
      if (path.endsWith("/result")) return json(markdownResult("run_other"));
      return json(structuredRun("run_other"));
    }));
    const user = userEvent.setup();
    await openWorkspace();
    const question = screen.getByRole("textbox", { name: "研究问题" });
    fireEvent.change(question, { target: { value: "Keep observing this question" } });
    const form = question.closest("form")!;
    act(() => {
      fireEvent.submit(form);
      fireEvent.submit(form);
    });
    await screen.findByText("正在提交");
    expect(writes).toHaveLength(1);
    acknowledge(json({
      run_id: "run_structured", segment_id: "segment", status: "started",
      thread_id: "demo-console-test", idempotent_replay: false
    }));
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("运行中"));

    await user.click(screen.getByRole("button", { name: "查找研究" }));
    await user.type(screen.getByRole("textbox", { name: "运行编号" }), "run_other");
    await user.click(screen.getByRole("button", { name: "打开研究" }));
    await screen.findByRole("button", { name: "阅读这份报告" });
    await user.click(screen.getByRole("button", { name: "返回首页" }));
    expect(screen.getByRole("status")).toHaveTextContent("运行中");
    expect(screen.getByRole("textbox", { name: "研究问题" })).toHaveValue("Keep observing this question");
    expect(writes).toHaveLength(1);
  });

  it("replays a frozen body and the same key after an uncertain create", async () => {
    const requests = fixture({ loseResponse: true });
    const user = userEvent.setup();
    await openWorkspace();
    await submit(user);
    await user.click(await screen.findByRole("button", { name: "核对同一请求" }));
    const retry = screen.getByRole("button", { name: "重试同一请求" });
    const posts = () => requests.filter((request) => request.method === "POST");
    expect(posts()).toHaveLength(1);
    expect(screen.queryByRole("button", { name: "开始研究" })).not.toBeInTheDocument();
    await user.click(retry);
    await screen.findByRole("button", { name: "阅读报告" });
    expect(posts()).toHaveLength(2);
    expect(posts()[1]).toEqual(posts()[0]);
  });

  it("recovers interrupted report reads with GET and does not label them as execution failure", async () => {
    const requests = fixture({ resultUnavailable: true });
    const user = userEvent.setup();
    await openWorkspace();
    await submit(user);
    await screen.findByText("报告读取中断");
    expect(screen.queryByText("研究失败")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "重读报告" }));
    await screen.findByText("报告已就绪");
    expect(requests.filter((request) => request.method === "POST")).toHaveLength(1);
    expect(requests.filter((request) => request.path.endsWith("/result"))).toHaveLength(2);
  });

  it.each([["blocked", "交付受阻"], ["review_required", "等待复核"]])(
    "renders %s without fetching or exposing a report",
    async (delivery, label) => {
      const requests = fixture({ delivery });
      await openWorkspace();
      await submit(userEvent.setup());
      await screen.findByText(label);
      expect(requests.some((request) => /\/(findings|result)$/.test(request.path))).toBe(false);
      expect(screen.queryByRole("button", { name: "阅读报告" })).not.toBeInTheDocument();
    }
  );

  it("opens an existing run using only GET and returns to the exact draft", async () => {
    const requests = fixture();
    const user = userEvent.setup();
    await openWorkspace();
    await user.type(screen.getByRole("textbox", { name: "研究问题" }), "Draft kept");
    await user.click(screen.getByRole("button", { name: "查找研究" }));
    await user.type(screen.getByRole("textbox", { name: "运行编号" }), "run_structured");
    await user.click(screen.getByRole("button", { name: "打开研究" }));
    await screen.findByRole("button", { name: "阅读这份报告" });
    await user.click(screen.getByRole("button", { name: "返回首页" }));
    expect(screen.getByRole("textbox", { name: "研究问题" })).toHaveValue("Draft kept");
    expect(requests.every((request) => request.method === "GET")).toBe(true);
  });

  it("prefills an explicitly edited retry without automatically creating another run", async () => {
    const requests = fixture({ failure: true });
    const user = userEvent.setup();
    await openWorkspace();
    await submit(user);
    await user.click(await screen.findByRole("button", { name: "查看原因" }));
    expect(screen.getByText("研究在执行阶段超时")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "编辑问题，另开研究" }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "研究问题" })).toHaveFocus());
    expect(screen.getByRole("textbox", { name: "研究问题" })).toHaveValue("  用户自己的问题\n🧭  ");
    expect(requests.filter((request) => request.method === "POST")).toHaveLength(1);
  });
});
