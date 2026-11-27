import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";

import Fieldwork from "./Fieldwork";

const api = "/api/fieldwork/projects/northstar";
const source = {
  id: "ev-1",
  material_id: "mat-1",
  title: "客户 IT 回函",
  source_id: "source-1",
  publication_id: "publication-1",
  revision: 3,
  material_version: 2,
  producer_run_id: "ingest-1",
  consumer_run_id: "dra-1",
  page_start: 2,
  page_end: 2,
  text: "允许用脱敏样本向客户演示。",
  sha256: "digest-1",
  byte_start: 41,
  byte_end: 80,
};
const before = {
  version: 1, proposal_id: null, headline: "先推进现场访谈，同步核实演示权限",
  summary: "已有约定，待书面确认。", items: [], evidence: [],
};
const proposal = {
  id: "proposal-1", dra_run_id: "dra-1", basis_revision: 2, status: "pending",
  material_id: "mat-1", headline: "先备妥脱敏样本", summary: "实时读取独立等待 IT 审批。",
  feedback: "", mode: "replay", evidence: [source],
  items: [{
    area: "demo", state: "proceed", priority: "high", action: "准备脱敏样本",
    owner: "试点负责人", reason: "书面回函明确了演示范围。", question: "", evidence_ids: ["ev-1"],
  }],
};
const initial = {
  id: "northstar", title: "北辰装备 · 现场服务助手", stage: "现场调查", revision: 1,
  sample_prepared: false, mode: "replay", confirmed: before, proposal: null,
  materials: [], deliverables: [],
};

afterEach(() => vi.unstubAllGlobals());

test("reads a PDF change through analysis, evidence, stale review reconciliation and a registered export", async () => {
  const file = new File(["%PDF-"], "reply.pdf", { type: "application/pdf" });
  const material = {
    id: "mat-1", title: "客户 IT 回函", sha256: "pdf-digest", active: true,
    source_id: source.source_id, publication_id: source.publication_id, revision: 3, producer_run_id: "ingest-1",
  };
  let project = { ...initial } as Omit<typeof initial, "proposal" | "materials" | "deliverables"> & {
    proposal: typeof proposal | null; materials: typeof material[]; deliverables: { version: number; sha256: string }[];
  };
  let reviewAttempts = 0;
  const requests: string[] = [];
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    requests.push(url);
    if (url === api) return Response.json(project);
    if (url.startsWith(api + "/materials?")) {
      expect(init?.body).toBe(file);
      expect(init?.headers).toEqual({ "Content-Type": "application/pdf" });
      expect(new URL(url, "http://localhost").searchParams.get("title")).toBe("客户 IT 回函");
      project = { ...project, revision: 2, materials: [material] };
      return Response.json(project);
    }
    if (url === api + "/analysis") {
      expect(JSON.parse(String(init?.body))).toEqual({ material_id: "mat-1" });
      project = { ...project, proposal };
      return Response.json(project);
    }
    if (url === api + "/proposals/proposal-1/evidence/ev-1/live") {
      return Response.json({ status: "unavailable", frozen: source, current: null, reason: "publication_changed" });
    }
    if (url === api + "/review") {
      expect(JSON.parse(String(init?.body))).toEqual({ proposal_id: "proposal-1", decision: "accept", feedback: "" });
      reviewAttempts += 1;
      project = { ...project, proposal: { ...proposal, status: "superseded" } };
      return Response.json({ detail: { code: "stale_proposal", message: "资料或项目已变化，请重新分析。" } }, { status: 409 });
    }
    if (url === api + "/history") {
      return Response.json({
        confirmed: [{ version: 1, proposal_id: null, headline: before.headline }],
        proposals: [{ id: "proposal-1", status: "superseded", headline: proposal.headline, material_id: "mat-1", feedback: "" }],
      });
    }
    if (url === api + "/proposals/proposal-1") return Response.json(project.proposal);
    throw new Error(`Unexpected request ${url}`);
  });
  render(<Fieldwork />);

  const user = userEvent.setup();
  expect(await screen.findByRole("heading", { name: "现场服务助手" })).toBeInTheDocument();
  expect(screen.getByText("离线回放")).toBeInTheDocument();
  await user.click(within(screen.getByRole("navigation", { name: "工作台导航" })).getByRole("button", { name: "变更收件箱" }));
  await user.type(screen.getByLabelText("资料名称"), "客户 IT 回函");
  await user.upload(screen.getByLabelText("PDF 文件"), file);
  await user.click(screen.getByRole("button", { name: "上传 PDF" }));
  await user.click(await screen.findByRole("button", { name: "分析材料" }));

  const review = await screen.findByRole("heading", { name: "阶段评审" });
  expect(review).toBeInTheDocument();
  expect(screen.getByText("先备妥脱敏样本")).toBeInTheDocument();
  const cite = screen.getByRole("button", { name: "查看依据：客户 IT 回函" });
  await user.click(cite);
  const evidence = screen.getByRole("region", { name: "冻结原句" });
  expect(within(evidence).getByText(source.text)).toBeInTheDocument();
  expect(within(evidence).getByText("资料版本 2 · 第 2 页")).toBeInTheDocument();
  await user.click(within(evidence).getByRole("button", { name: "核对当前回读" }));
  expect(await within(evidence).findByText("当前版本无法回读这条原句，仍可核对冻结原句。")).toBeInTheDocument();
  screen.getByRole("main").focus();
  await user.keyboard("{Escape}");
  expect(evidence).not.toBeInTheDocument();
  expect(cite).toHaveFocus();

  const initialReads = requests.filter((url) => url === api).length;
  await user.click(screen.getByRole("button", { name: "采纳整份建议" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("资料或项目已变化，请重新分析。");
  expect(reviewAttempts).toBe(1);
  expect(screen.queryByRole("button", { name: "采纳整份建议" })).toBeNull();
  expect(await screen.findByText("已过期")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "查看依据：客户 IT 回函" })).toBeInTheDocument();

  project = { ...project, deliverables: [{ version: 1, sha256: "export-digest" }] };
  await user.click(screen.getByRole("button", { name: "重新读取项目" }));
  await user.click(screen.getByRole("button", { name: "交付成果" }));
  expect(await screen.findByRole("link", { name: "打开 HTML" })).toHaveAttribute("href", api + "/exports/1.html");
  expect(screen.getByRole("link", { name: "下载 Markdown" })).toHaveAttribute("href", api + "/exports/1.md");
  expect(requests.filter((url) => url === api)).toHaveLength(initialReads + 2);
});

test("flags only confirmed actions that rely on replaced material and restores the interrupted upload selection", async () => {
  const interviewEvidence = { ...source, id: "seed-1", material_id: "seed", producer_run_id: "seed" };
  const interview = {
    ...proposal.items[0], area: "interview", action: "继续访谈", evidence_ids: ["seed-1"],
  };
  const retired = { id: "mat-1", title: source.title, revision: 3, material_version: 2, active: false };
  const active = { ...retired, id: "mat-2", material_version: 3, active: true };
  const updated = {
    ...initial,
    confirmed: { ...proposal, version: 2, proposal_id: proposal.id, items: [...proposal.items, interview], evidence: [source, interviewEvidence] },
    materials: [active, retired],
    intake: { title: "IT 补充回函", replace: "mat-2", sha256: "pending-digest", state: "pending", error_code: null },
  };
  vi.stubGlobal("fetch", async () => Response.json(updated));

  render(<Fieldwork />);
  const user = userEvent.setup();
  const retiredAction = (await screen.findByText("准备脱敏样本")).closest("li")!;
  expect(within(retiredAction).getByText("依据已替代，待复核")).toBeInTheDocument();
  expect(within(retiredAction).queryByText("可继续")).toBeNull();
  const continuingAction = screen.getByText("继续访谈").closest("li")!;
  expect(within(continuingAction).getByText("可继续")).toBeInTheDocument();
  await user.click(within(screen.getByRole("navigation", { name: "工作台导航" })).getByRole("button", { name: "阶段工作区" }));
  expect(screen.queryByRole("button", { name: "记录样本已准备" })).toBeNull();

  await user.click(within(screen.getByRole("navigation", { name: "工作台导航" })).getByRole("button", { name: "变更收件箱" }));
  await user.click(screen.getByRole("button", { name: "恢复本次提交" }));
  expect(screen.getByLabelText("录入方式")).toHaveValue("mat-2");
  expect(screen.getByLabelText("资料名称")).toHaveValue("IT 补充回函");
  expect(screen.getByRole("button", { name: "分析材料" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "上传 PDF" })).toBeDisabled();
});
