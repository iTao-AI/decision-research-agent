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
  const hero = screen.getByRole("heading", { name: /把公开资料整理成.*有出处的研究报告/ });
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
  expect(screen.getByRole("heading", { name: /把公开资料整理成.*有出处的研究报告/ })).toBe(hero);
  expect(screen.getByRole("textbox", { name: "研究问题" })).toBe(question);
  expect(submit).toHaveFocus();
  expect(window.location.href).toBe(initialUrl);
  expect(screen.queryByRole("heading", { name: "来源绑定的候选结论" })).not.toBeInTheDocument();
  const report = screen.getByRole("button", { name: "阅读报告" });
  await user.click(report);
  const panel = screen.getByRole("region", { name: "研究报告" });
  expect(within(panel).getByRole("heading", { name: "来源绑定的候选结论" })).toBeInTheDocument();
  await user.click(within(panel).getByRole("button", { name: "查看来源 1" }));
  const citation = within(panel).getByRole("button", { name: "查看来源 1" });
  await user.click(within(panel).getByRole("button", { name: "返回引用处" }));
  expect(citation).toHaveFocus();
  await user.click(within(panel).getByRole("button", { name: "返回首页" }));
  expect(report).toHaveFocus();
});

it("shows execution failure visibly and reveals only observed retained text when opened", async () => {
  service({ fail: true });
  const { user, submit, question } = await start();
  await user.click(submit);
  const inspect = await screen.findByRole("button", { name: "查看原因" });
  expect(screen.getByRole("status")).toHaveTextContent("研究失败");
  expect(screen.queryByText("真的留存在本次研究中的原文")).not.toBeInTheDocument();
  expect(question).toHaveValue("保留的原问题");
  await user.click(inspect);
  expect(screen.getByText("真的留存在本次研究中的原文")).toBeInTheDocument();
});

it("preserves the current run while opening another by number", async () => {
  const api = service({ hold: true });
  const { user, submit } = await start();
  await user.click(submit);
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("运行中"));
  await user.click(screen.getByRole("button", { name: "查找研究" }));
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
