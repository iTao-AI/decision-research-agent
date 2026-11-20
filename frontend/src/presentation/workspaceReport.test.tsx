import { createRef } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { parseResearchFindings } from "../researchFindings";
import { parseRunResult } from "../runProjection";
import { findingsResponse, markdownResult } from "../test/researchFindingsFixture";
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
    await user.click(screen.getByText("Raw", { selector: "summary" }));
    expect(original).toBeVisible();
    expect(original?.textContent).toBe(markdown);
    await user.click(screen.getByRole("button", { name: "Download Markdown" }));
    expect(filename).toBe("research-report.md");
    expect(downloaded?.type).toBe("text/markdown;charset=utf-8");
    const bytes = new Uint8Array(await downloaded!.arrayBuffer());
    expect(Array.from(bytes)).toEqual(Array.from(new TextEncoder().encode(markdown)));
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
