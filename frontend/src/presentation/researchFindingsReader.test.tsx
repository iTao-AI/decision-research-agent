import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { findingsResponse } from "../test/researchFindingsFixture";
import { parseResearchFindings } from "../researchFindings";
import { ResearchFindingsReader } from "./researchFindingsReader";

afterEach(() => vi.restoreAllMocks());

describe("structured source inspection", () => {
  it("shows observed dispositions for all five accepted questions with their sources and unresolved reasons", () => {
    const value = findingsResponse();
    value.report.questions = [
      { question_id: "q1", text: "Accepted first" }, { question_id: "q3", text: "Accepted second" },
      { question_id: "q5", text: "Accepted third" }, { question_id: "q7", text: "Accepted fourth" },
      { question_id: "q9", text: "Accepted fifth" }
    ];
    const baseFinding = value.report.findings[0];
    value.report.findings = [baseFinding, { ...baseFinding, finding_id: "f2", question_id: "q5", statement: "Third candidate" },
      { ...baseFinding, finding_id: "f3", question_id: "q9", statement: "Fifth candidate" }];
    value.report.dispositions = [
      { question_id: "q1", status: "candidate_findings" }, { question_id: "q3", status: "unresolved", reason: "Second lacks evidence" },
      { question_id: "q5", status: "candidate_findings" }, { question_id: "q7", status: "unresolved", reason: "Fourth lacks evidence" },
      { question_id: "q9", status: "candidate_findings" }
    ];
    value.artifact.content = JSON.stringify(value.report);
    render(<ResearchFindingsReader language="en" findings={parseResearchFindings(value, "run_structured")} />);
    const questions = screen.getByRole("region", { name: "Accepted research questions" });
    expect(within(questions).getAllByText("Candidate findings")).toHaveLength(3);
    expect(within(questions).getAllByText("Unresolved")).toHaveLength(2);
    expect(screen.getByText("Third candidate")).toBeInTheDocument();
    expect(screen.getByText("Fifth candidate")).toBeInTheDocument();
    expect(screen.getByText("Second lacks evidence")).toBeInTheDocument();
    expect(screen.getByText("Fourth lacks evidence")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "https://example.com/source" })).toHaveLength(3);
    expect(screen.getByText("两个来源的更新时间存在矛盾")).toBeInTheDocument();
  });

  it("renders every model/source string as text and suppresses unsafe source actions", async () => {
    const value = findingsResponse();
    const ref = value.report.findings[0].references[0];
    Object.assign(ref, { source_url: "javascript:alert(1)", source_identity: "data:text/html,<script>x</script>",
      snippet: '<img src=x onerror="alert(1)"> tail', excerpt: '<img src=x onerror="alert(1)">', excerpt_start: 0, excerpt_end: 30 });
    value.report.findings[0].statement = "[candidate](javascript:alert(1)) <script>bad()</script>";
    value.report.questions[0].text = "<iframe>question</iframe>";
    value.report.reported_contradictions = ["<svg onload=alert(1)>contradiction</svg>"];
    value.report.limitations = ["<script>limitation</script>"];
    value.artifact.content = JSON.stringify(value.report);
    const { container } = render(<ResearchFindingsReader language="zh" findings={parseResearchFindings(value, "run_structured")} />);
    expect(screen.getByText(value.report.findings[0].statement)).toBeInTheDocument();
    expect(screen.getAllByText(value.report.questions[0].text)).toHaveLength(2);
    expect(screen.getByText(value.report.reported_contradictions[0])).toBeInTheDocument();
    expect(screen.getByText("javascript:alert(1)")).toBeInTheDocument();
    expect(container.querySelector("script, img, iframe, svg, a[href^='javascript:'], a[href^='data:']")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "查看完整持久化片段" }));
    expect(screen.getByText(ref.snippet)).toBeInTheDocument();
  });

  it("opens the full long Unicode snippet by keyboard at narrow viewport and restores inspection focus", async () => {
    const originalWidth = window.innerWidth;
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
    const scroll = vi.fn();
    const originalScroll = HTMLElement.prototype.scrollIntoView;
    HTMLElement.prototype.scrollIntoView = scroll;
    try {
      const value = findingsResponse();
      const ref = value.report.findings[0].references[0];
      ref.snippet += "余😀".repeat(4000);
      value.artifact.content = JSON.stringify(value.report);
      const user = userEvent.setup();
      render(<ResearchFindingsReader language="en" findings={parseResearchFindings(value, "run_structured")} />);
      const inspect = screen.getByRole("button", { name: "Inspect full persisted snippet" });
      inspect.focus(); await user.keyboard("{Enter}");
      const region = screen.getByRole("region", { name: "Full persisted snippet" });
      expect(region).toHaveFocus();
      expect(within(region).getByText(ref.snippet).textContent).toBe(ref.snippet);
      expect(inspect).toHaveAttribute("aria-expanded", "true");
      expect(scroll).toHaveBeenCalled();
      await user.tab();
      expect(screen.getByRole("button", { name: "Return to excerpt" })).toHaveFocus();
      await user.keyboard("{Enter}");
      expect(inspect).toHaveFocus();
      expect(inspect).toHaveAttribute("aria-expanded", "false");
    } finally {
      Object.defineProperty(window, "innerWidth", { configurable: true, value: originalWidth });
      if (originalScroll) HTMLElement.prototype.scrollIntoView = originalScroll;
      else Reflect.deleteProperty(HTMLElement.prototype, "scrollIntoView");
    }
  });
});
