import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Observation, ResultView } from "../consoleProjection";
import {
  downloadArtifact,
  ResultReader,
  safeHttpUrl,
  sanitizeArtifactFilename
} from "./resultReader";

const CONTENT = "# 标题\n\n正文保留原始字节。\n\n- 第一项\n\n```text\n<safe-code>\n```";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ResultReader", () => {
  it("renders safe formatted and exact raw views without interpreting HTML", async () => {
    const user = userEvent.setup();
    const result = observedResult("# 标题\n\n<script>alert('x')</script>\n\n1. 一项");

    const { container } = render(<ResultReader language="zh" mode="static" result={result} />);

    expect(screen.getByRole("heading", { name: "标题" })).toBeInTheDocument();
    expect(screen.getByText("<script>alert('x')</script>")).toBeInTheDocument();
    expect(container.querySelector("script")).not.toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "原文" }));
    expect(container.querySelector(".raw-artifact")?.textContent).toBe(
      "# 标题\n\n<script>alert('x')</script>\n\n1. 一项"
    );
  });

  it("downloads the exact report bytes with a sanitized filename", async () => {
    const createObjectUrl = vi.fn((_blob: Blob) => "blob:research-report");
    const revokeObjectUrl = vi.fn();
    const originalCreateObjectUrl = URL.createObjectURL;
    const originalRevokeObjectUrl = URL.revokeObjectURL;
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: createObjectUrl
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: revokeObjectUrl
    });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    let clickedDownload = "";
    click.mockImplementation(function (this: HTMLAnchorElement) {
      clickedDownload = this.download;
    });

    expect(downloadArtifact(CONTENT, "../客服报告?.md")).toBe(true);
    const blob = createObjectUrl.mock.calls[0]?.[0] as Blob | undefined;
    expect(blob).toBeInstanceOf(Blob);
    await expect(blob?.text()).resolves.toBe(CONTENT);
    expect(clickedDownload).toBe("research-report.md");
    expect(revokeObjectUrl).toHaveBeenCalledWith("blob:research-report");

    if (originalCreateObjectUrl) {
      Object.defineProperty(URL, "createObjectURL", { configurable: true, value: originalCreateObjectUrl });
    } else {
      Reflect.deleteProperty(URL, "createObjectURL");
    }
    if (originalRevokeObjectUrl) {
      Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: originalRevokeObjectUrl });
    } else {
      Reflect.deleteProperty(URL, "revokeObjectURL");
    }
  });

  it("does not offer a download for an unavailable result", () => {
    render(<ResultReader language="zh" mode="static" result={{ kind: "not_applicable" }} />);

    expect(screen.getByText("报告暂不可用")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "下载报告" })).not.toBeInTheDocument();
    expect(screen.getByText("当前状态没有可交付的 canonical result，因此没有下载操作。")).toBeInTheDocument();
  });
});

describe("result safety helpers", () => {
  it.each([
    ["../客服报告?.md", "research-report.md"],
    ["", "research-report.md"],
    ["brief", "brief.md"],
    ["BRIEF.MD", "brief.md"]
  ])("sanitizes %s", (value, expected) => {
    expect(sanitizeArtifactFilename(value)).toBe(expected);
  });

  it.each([
    ["https://example.com/source", true],
    ["http://localhost:8000/source", true],
    ["javascript:alert(1)", false],
    ["data:text/plain,unsafe", false],
    ["https://user:secret@example.com/source", false]
  ])("accepts only safe HTTP(S) source URLs: %s", (value, accepted) => {
    expect(Boolean(safeHttpUrl(value))).toBe(accepted);
  });
});

function observedResult(content: string): Observation<ResultView> {
  return {
    kind: "observed",
    value: {
      runId: "run_reader_test",
      executionStatus: { kind: "observed", value: "completed" },
      deliveryStatus: { kind: "observed", value: "ready" },
      artifact: {
        artifactId: "reader-test.md",
        kind: { kind: "observed", value: "research_report_markdown" },
        mediaType: "text/markdown",
        contentHash: "sha256:reader-test",
        revision: { kind: "observed", value: "publication_rev_1" },
        safety: { kind: "observed", value: "hash verified" },
        content
      }
    }
  };
}
