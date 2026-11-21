import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { afterEach, expect, it, vi } from "vitest";
import App from "./App";
import { findingsResponse, markdownResult, structuredRun } from "./test/researchFindingsFixture";

afterEach(() => vi.unstubAllGlobals());

const json = (value: unknown) => Response.json(value);
const options = { randomUUID: () => "modular", pollIntervalMs: 1 };

function service({ hold = false, fail = false, interrupt = false } = {}) {
  const reads: string[] = [];
  let writes = 0;
  let ready = !hold;
  let disconnected = interrupt;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(String(input)).pathname;
    reads.push(path);
    if (path === "/health") return json({ service: "decision-research-agent", status: "ok" });
    if (init?.method === "POST") {
      writes += 1;
      return json({ run_id: "run_home", segment_id: "seg", status: "started", thread_id: "demo-console-modular", idempotent_replay: false });
    }
    const run = path.includes("run_other") ? "run_other" : "run_home";
    if (path.endsWith("/findings")) {
      const accepted = findingsResponse(run);
      if (run === "run_other") {
        accepted.report.questions[0].text = "另一个被查阅的问题";
        accepted.artifact.content = JSON.stringify(accepted.report);
      }
      return json(accepted);
    }
    if (path.endsWith("/result")) return json(markdownResult(run));
    if (run === "run_home" && disconnected) throw new TypeError("read disconnected");
    if (run === "run_home" && fail) return json({
      ...structuredRun(run, "failed"), execution_status: "failed",
      failure_cause: { schema_version: "dra.run-failure-cause.v1", observation_status: "observed", phase: "execution", code: "run_timeout", recorded_at: "2026-11-20T12:00:00Z" },
      evidence: [{ evidence_id: "e1", source_url: "https://example.com/report", source_identity: "example.com/report", evidence_fingerprint: "a", citation_status: "collected", verification_status: "unverified", snippet: "真的留存在本次研究中的原文" }]
    });
    if (run === "run_home" && !ready) return json({ ...structuredRun(run, "pending"), execution_status: "running" });
    return json(structuredRun(run));
  }));
  return { writes: () => writes, reads, finish: () => { ready = true; }, reconnect: () => { disconnected = false; } };
}

async function start() {
  render(<StrictMode><App liveOptions={options} /></StrictMode>);
  await screen.findByRole("button", { name: /服务已连接/ });
  const user = userEvent.setup();
  const question = screen.getByRole("textbox", { name: "研究问题" });
  const submit = screen.getByRole("button", { name: "开始研究" });
  await user.type(question, "保留的原问题");
  return { user, question, submit };
}

it("keeps the home, exact composer and focused action in place from submit to delivery", async () => {
  const api = service({ hold: true });
  const { user, question, submit } = await start();
  const hero = screen.getByRole("heading", { name: "你想研究什么？" });
  const initialUrl = window.location.href;
  expect(screen.getByRole("button", { name: /多问题比较/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /核对结论出处/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /跟进未解问题/ })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "示例报告" })).not.toBeInTheDocument();
  await user.click(submit);
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("运行中"));
  expect(question).toHaveValue("保留的原问题");
  expect(question).toHaveAttribute("readonly");
  expect(submit).toHaveFocus();
  expect(screen.getByRole("button", { name: "已提交" })).toBe(submit);
  fireEvent.submit(question.closest("form")!);
  expect(api.writes()).toBe(1);
  api.finish();
  await screen.findByRole("button", { name: "阅读报告" });
  expect(screen.getByRole("heading", { name: "你想研究什么？" })).toBe(hero);
  expect(screen.getByRole("textbox", { name: "研究问题" })).toBe(question);
  expect(submit).toHaveFocus();
  expect(window.location.href).toBe(initialUrl);
  expect(screen.queryByRole("heading", { name: "来源绑定的候选结论" })).not.toBeInTheDocument();
  const report = screen.getByRole("button", { name: "阅读报告" });
  await user.click(report);
  const panel = screen.getByRole("region", { name: "研究报告" });
  expect(within(panel).getByRole("heading", { name: "研究结论" })).toBeInTheDocument();
  expect(window.location.search).toBe("?report=run_home");
  await user.click(within(panel).getByRole("button", { name: "复制报告链接" }));
  expect(await navigator.clipboard.readText()).toBe(`${window.location.origin}/?report=run_home`);
  await user.click(within(panel).getByRole("button", { name: "查看来源 1" }));
  const citation = within(panel).getByRole("button", { name: "查看来源 1" });
  await user.click(within(panel).getByRole("button", { name: "返回引用处" }));
  expect(citation).toHaveFocus();
  await user.click(within(panel).getByRole("button", { name: "返回首页" }));
  expect(report).toHaveFocus();
  expect(window.location.search).toBe("");
});

it("shows execution failure visibly and reveals only observed retained text when opened", async () => {
  service({ fail: true });
  const { user, submit, question } = await start();
  await user.click(submit);
  const inspect = await screen.findByRole("button", { name: "查看原因" });
  expect(screen.getByRole("status")).toHaveTextContent("执行超时");
  expect(screen.queryByText("真的留存在本次研究中的原文")).not.toBeInTheDocument();
  expect(question).toHaveValue("保留的原问题");
  await user.click(inspect);
  expect(screen.getByText("真的留存在本次研究中的原文")).not.toBeVisible();
  expect(screen.getByText("停止阶段")).toBeVisible();
});

it("preserves the current run while opening another by number", async () => {
  const api = service({ hold: true });
  const { user, submit } = await start();
  await user.click(submit);
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("运行中"));
  await user.click(screen.getByRole("button", { name: "按编号打开研究" }));
  const dialog = screen.getByRole("dialog", { name: "查找研究" });
  await user.type(within(dialog).getByRole("textbox", { name: "运行编号" }), "run_other");
  await user.click(within(dialog).getByRole("button", { name: "打开研究" }));
  const known = screen.getByRole("region", { name: "已有研究" });
  await within(known).findByRole("button", { name: "阅读这份报告" });
  expect(within(known).getByRole("heading", { name: "另一个被查阅的问题" })).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("运行中");
  expect(api.writes()).toBe(1);
  act(() => api.finish());
  await screen.findByRole("button", { name: "阅读报告" });
  expect(known).toBeInTheDocument();
});

it("recovers an interrupted status with GET and preserves the submitted draft", async () => {
  const api = service({ interrupt: true });
  const { user, submit, question } = await start();
  await user.click(submit);
  const resume = await screen.findByRole("button", { name: "恢复查看" });
  expect(screen.getByRole("status")).toHaveTextContent("状态读取中断");
  api.reconnect();
  await user.click(resume);
  await screen.findByRole("button", { name: "阅读报告" });
  expect(question).toHaveValue("保留的原问题");
  expect(api.writes()).toBe(1);
});

it("explains the report structure on request without presenting sample findings or creating a run", async () => {
  const api = service();
  const { user, question } = await start();
  const outline = screen.getByRole("button", { name: "看看报告如何引用原文" });
  expect(screen.queryByText("结构示意")).not.toBeInTheDocument();
  await user.click(outline);
  const panel = screen.getByRole("region", { name: "报告怎样引用原文" });
  expect(within(panel).getByText("结构示意")).toBeVisible();
  const reference = within(panel).getByRole("button", { name: "查看引文 1 的原文位置" });
  await user.click(reference);
  expect(within(panel).getByRole("heading", { name: "引用原文的位置" })).toHaveFocus();
  expect(within(panel).queryByRole("link")).not.toBeInTheDocument();
  await user.click(within(panel).getByRole("button", { name: "返回引文" }));
  expect(reference).toHaveFocus();
  await user.click(within(panel).getByRole("button", { name: "返回首页" }));
  expect(outline).toHaveFocus();
  expect(question).toHaveValue("保留的原问题");
  expect(api.writes()).toBe(0);
});

it("offers the same explanation from the tools directory without a delivered report", async () => {
  service();
  const { user } = await start();
  await user.click(screen.getByRole("button", { name: /核对结论出处/ }));
  const sources = screen.getByRole("region", { name: "核对结论出处" });
  const outline = within(sources).getByRole("button", { name: "报告怎样引用原文" });
  await user.click(outline);
  const panel = screen.getByRole("region", { name: "报告怎样引用原文" });
  expect(within(panel).getByText("结构示意")).toBeVisible();
  await user.click(within(panel).getByRole("button", { name: "返回上一层" }));
  expect(outline).toHaveFocus();
});

it("opens the current canonical sources rather than the explanation when a report is delivered", async () => {
  const api = service();
  const { user, submit, question } = await start();
  await user.click(submit);
  await screen.findByRole("button", { name: "阅读报告" });
  const outline = screen.getByRole("button", { name: "查看本次引用" });
  await user.click(outline);
  const sources = screen.getByRole("region", { name: "核对结论出处" });
  expect(within(sources).queryByText("结构示意")).not.toBeInTheDocument();
  expect(within(sources).getByText("😀精确片段")).toBeVisible();
  await user.click(within(sources).getByRole("button", { name: "返回首页" }));
  expect(outline).toHaveFocus();
  expect(question).toHaveValue("保留的原问题");
  expect(api.writes()).toBe(1);
});

it("reopens a shared report through read-only requests and drafts a follow-up with its original scope", async () => {
  const api = service();
  window.history.replaceState(null, "", "/?report=run_home");
  render(<StrictMode><App liveOptions={options} /></StrictMode>);
  const user = userEvent.setup();
  const report = screen.getByRole("region", { name: "研究报告" });
  await user.click(await within(report).findByRole("button", { name: "待查 1 项" }));
  const follow = within(report).getByRole("button", { name: "继续研究" });
  expect(api.reads).toContain("/api/runs/run_home/findings");
  expect(api.writes()).toBe(0);
  await user.click(follow);
  const draft = within(screen.getByRole("region", { name: "新研究草稿" }));
  expect(draft.getByRole("textbox", { name: "新研究问题 1" })).toHaveValue("研究问题");
  expect(draft.getByRole("textbox", { name: "新研究问题 2" })).toHaveValue("未解决问题");
  expect(window.location.search).toBe("?report=run_home");
  expect(api.writes()).toBe(0);
  await user.click(screen.getByRole("button", { name: "返回原报告" }));
  expect(follow).toHaveFocus();
  expect(screen.getByRole("region", { name: "研究报告" })).toBe(report);
});

it("does not contact a URL-supplied service or look up an invalid report identifier", async () => {
  const api = service();
  window.history.replaceState(null, "", "/?report=https%3A%2F%2Fother.invalid&endpoint=https%3A%2F%2Fother.invalid");
  render(<StrictMode><App liveOptions={options} /></StrictMode>);
  await screen.findByRole("button", { name: /服务已连接/ });
  expect(api.reads).toEqual(["/health"]);
  expect(api.writes()).toBe(0);
  expect(screen.queryByRole("region", { name: "研究报告" })).not.toBeInTheDocument();
});

it("retains an unopened report link while correcting an offline local connection", async () => {
  const api = service();
  const fixtureFetch = window.fetch;
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    if (new URL(String(input)).port !== "9001") return Promise.reject(new TypeError("offline"));
    return fixtureFetch(input, init);
  }));
  window.history.replaceState(null, "", "/?report=run_home");
  render(<StrictMode><App liveOptions={options} /></StrictMode>);
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "服务未连接，修改连接" }));
  const dialog = within(screen.getByRole("dialog", { name: "连接设置" }));
  fireEvent.change(dialog.getByRole("textbox", { name: "本地后端地址" }), { target: { value: "http://127.0.0.1:9001" } });
  await user.click(dialog.getByRole("button", { name: "保存连接" }));
  const report = await screen.findByRole("region", { name: "研究报告" });
  expect(await within(report).findByText("来源绑定的候选结论")).toBeVisible();
  expect(window.location.search).toBe("?report=run_home");
  expect(api.writes()).toBe(0);
});
