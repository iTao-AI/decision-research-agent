import { createRef } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { parseResearchFindings } from "../researchFindings";
import { parseRunResult, parseRunProjection } from "../runProjection";
import { findingsResponse, markdownResult, structuredRun } from "../test/researchFindingsFixture";
import { WorkspaceReport } from "./workspaceReport";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("WorkspaceReport", () => {
  it("makes the generic canonical Markdown safely readable and focusable in place", () => {
    const raw = markdownResult("run_generic");
    raw.artifact.content = "# 可读报告\n\n- 已知事实\n\n<script>alert(1)</script>";
    const ref = createRef<HTMLElement>();
    const { container } = render(<WorkspaceReport language="zh" result={parseRunResult(raw)} reportRef={ref} />);
    const article = screen.getByRole("article", { name: "研究报告" });
    expect(within(article).getByRole("heading", { name: "可读报告" })).toBeVisible();
    expect(within(article).getByRole("listitem")).toHaveTextContent("已知事实");
    expect(within(article).getByText("<script>alert(1)</script>")).toBeVisible();
    expect(container.querySelector("script")).toBeNull();
    ref.current?.focus();
    expect(article).toHaveFocus();
    expect(within(article).queryByRole("button", { name: "查看来源 1" })).not.toBeInTheDocument();
  });

  it("opens the exact original Markdown for reading and downloads its unchanged UTF-8 bytes", async () => {
    const raw = markdownResult();
    const markdown = "# Canonical report\r\n\r\n中😀e\u0301\r\n";
    raw.artifact.content = markdown;
    const findings = parseResearchFindings(findingsResponse(), raw.run_id);
    let downloaded: Blob | undefined;
    class DownloadURL extends URL {
      static createObjectURL(blob: Blob) {
        downloaded = blob;
        return "blob:workspace-report";
      }

      static revokeObjectURL() {}
    }
    vi.stubGlobal("URL", DownloadURL);
    let filename: string | undefined;
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      filename = this.download;
    });
    const user = userEvent.setup();
    const { container } = render(<WorkspaceReport language="en" result={parseRunResult(raw)} findings={findings} />);

    const first = screen.getByRole("region", { name: "研究问题" });
    expect(within(first).getByText("来源绑定的候选结论")).toBeVisible();
    expect(within(first).getByRole("button", { name: "View source 1" })).toBeVisible();
    expect(within(screen.getByRole("region", { name: "未解决问题" })).getByText("证据不足")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Canonical report" })).not.toBeInTheDocument();
    const original = container.querySelector(".dw-report-raw pre");
    expect(original).not.toBeVisible();
    await user.click(screen.getByText("View original report", { selector: "summary" }));
    expect(original).toBeVisible();
    expect(original?.textContent).toBe(markdown);
    await user.click(screen.getByRole("button", { name: "Download Markdown" }));
    expect(filename).toBe("research-report.md");
    expect(downloaded?.type).toBe("text/markdown;charset=utf-8");
    const bytes = new Uint8Array(await downloaded!.arrayBuffer());
    expect(Array.from(bytes)).toEqual(Array.from(new TextEncoder().encode(markdown)));
  });

  it("opens a real citation from the source entry and distinguishes citation locations, document identity and verification", async () => {
    const response = findingsResponse();
    response.report.questions[0].text = "For Ruff 0.14.6, which configuration applies with automatic discovery?";
    const reference = response.report.findings[0].references[0];
    const revision = "59c6cb521d26380120f8522476fd09d296bf4f2e";
    const url = `https://github.com/astral-sh/ruff/blob/${revision}/docs/configuration.md`;
    Object.assign(reference, { source_url: url, source_identity: url });
    response.report.findings.push({ ...response.report.findings[0], finding_id: "f2" });
    response.artifact.content = JSON.stringify(response.report);
    const run = parseRunProjection({ ...structuredRun(), evidence: [
      { ...reference, citation_status: "cited", verification_status: "unverified" }
    ] });
    const user = userEvent.setup();
    render(<WorkspaceReport language="en" result={parseRunResult(markdownResult())}
      findings={parseResearchFindings(response, response.run_id)} run={run} initialView="sources" />);

    expect(screen.getByRole("heading", { name: "Ruff 0.14.6" })).toBeVisible();
    expect(screen.getByRole("button", { name: "2 citations · 1 source" })).toBeVisible();
    expect(screen.getByText(response.report.questions[0].text, { selector: "p" })).not.toBeVisible();
    const source = screen.getByRole("complementary", { name: "Bound source 1" });
    expect(source).toHaveFocus();
    expect(within(source).getByRole("heading", { name: "ruff / docs/configuration.md" })).toBeVisible();
    expect(within(source).getByText("59c6cb5")).toBeVisible();
    expect(within(source).getByText("Passage located · Independent verification unconfirmed")).toBeVisible();
    expect(within(source).getByRole("link", { name: "Open source webpage" })).toHaveAttribute("href", url);
    await user.click(within(source).getByRole("button", { name: "Expand saved excerpt" }));
    expect(within(source).getByRole("region", { name: "Saved excerpt" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(within(source).getByRole("button", { name: "Expand saved excerpt" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.getByRole("button", { name: "View source 1" })).toHaveFocus();
  });

  it("returns a direct source visit to the first citation at the opening reading position", async () => {
    const reference = parseResearchFindings(findingsResponse(), "run_structured");
    const originalScroll = HTMLElement.prototype.scrollIntoView;
    HTMLElement.prototype.scrollIntoView = function () {
      const scroller = this.closest<HTMLElement>("#reader-scroll");
      if (scroller) scroller.scrollTop = 300;
    };
    try {
      const { container } = render(<div id="reader-scroll" style={{ overflowY: "auto" }}>
        <WorkspaceReport language="en" result={parseRunResult(markdownResult())} findings={reference} initialView="sources" />
      </div>);
      const scroller = container.querySelector("#reader-scroll")!;
      expect(scroller.scrollTop).toBe(300);
      await userEvent.keyboard("{Escape}");
      expect(screen.getByRole("button", { name: "View source 1" })).toHaveFocus();
      expect(scroller.scrollTop).toBe(0);
    } finally {
      if (originalScroll) HTMLElement.prototype.scrollIntoView = originalScroll;
      else Reflect.deleteProperty(HTMLElement.prototype, "scrollIntoView");
    }
  });

  it("focuses the unresolved section and invokes the adjacent follow-up with its original question ID", async () => {
    const response = findingsResponse();
    const user = userEvent.setup();
    const follow = vi.fn();
    const { rerender } = render(<WorkspaceReport language="zh" result={parseRunResult(markdownResult())}
      findings={parseResearchFindings(response, response.run_id)} initialView="unresolved" onFollowQuestion={follow} />);

    expect(screen.getByRole("region", { name: "待查问题" })).toHaveFocus();
    const conditions = screen.getByRole("region", { name: "适用条件与限制" });
    expect(within(conditions).getByText(response.report.limitations[0])).toBeVisible();
    expect(conditions.compareDocumentPosition(screen.getByRole("region", { name: "待查问题" })) &
      Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const action = within(screen.getByRole("region", { name: "未解决问题" })).getByRole("button", { name: "继续研究" });
    await user.click(action);
    expect(follow).toHaveBeenCalledWith("q2", action);

    const zero = findingsResponse("run_zero");
    zero.report.questions.splice(1);
    zero.report.dispositions.splice(1);
    zero.artifact.content = JSON.stringify(zero.report);
    rerender(<WorkspaceReport language="zh" result={parseRunResult(markdownResult("run_zero"))}
      findings={parseResearchFindings(zero, zero.run_id)} initialView="unresolved" onFollowQuestion={follow} />);
    expect(screen.getByText("待查 0 项")).toBeVisible();
    expect(screen.queryByRole("button", { name: "继续研究" })).not.toBeInTheDocument();
  });

  it("never presents findings from a different run with the current canonical report", () => {
    const result = parseRunResult(markdownResult("run_current"));
    const foreign = parseResearchFindings(findingsResponse("run_previous"), "run_previous");
    render(<WorkspaceReport language="en" result={result} findings={foreign} />);

    expect(screen.getByRole("heading", { name: "Canonical report" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "View source 1" })).not.toBeInTheDocument();
    expect(screen.queryByText("证据不足")).not.toBeInTheDocument();
  });
});
