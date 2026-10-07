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
    const directory = screen.getByRole("navigation", { name: "Question directory" });
    expect(within(directory).getAllByRole("button")).toHaveLength(5);
    expect(within(screen.getByRole("region", { name: "Accepted third" })).getByText("Third candidate")).toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Accepted fifth" })).getByText("Fifth candidate")).toBeInTheDocument();
    const second = screen.getByRole("region", { name: "Accepted second" });
    expect(within(second).getByText("Second lacks evidence")).toBeInTheDocument();
    expect(within(second).getByText("Unresolved")).toBeInTheDocument();
    expect(within(second).queryByRole("link")).not.toBeInTheDocument();
    expect(within(screen.getByRole("region", { name: "Accepted fourth" })).getByText("Fourth lacks evidence")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "https://example.com/source" })).toHaveLength(3);
    expect(within(screen.getByRole("region", { name: "Model-reported contradictions" })).getByText("两个来源的更新时间存在矛盾")).toBeInTheDocument();
    for (const question of value.report.questions) {
      const section = screen.getByRole("region", { name: question.text });
      expect(within(section).queryByText("两个来源的更新时间存在矛盾")).not.toBeInTheDocument();
      expect(within(section).queryByText("片段绑定不证明结论真实")).not.toBeInTheDocument();
    }
  });

  it("keeps multiple findings and sources together for a single accepted question", () => {
    const value = findingsResponse();
    value.report.questions = value.report.questions.slice(0, 1);
    value.report.dispositions = value.report.dispositions.slice(0, 1);
    value.report.findings.push({ ...value.report.findings[0], finding_id: "f2", statement: "Second observed candidate" });
    value.artifact.content = JSON.stringify(value.report);
    render(<ResearchFindingsReader language="en" findings={parseResearchFindings(value, "run_structured")} />);
    expect(within(screen.getByRole("navigation", { name: "Question directory" })).getAllByRole("button")).toHaveLength(1);
    const question = screen.getByRole("region", { name: "研究问题" });
    expect(within(question).getByText("来源绑定的候选结论")).toBeInTheDocument();
    expect(within(question).getByText("Second observed candidate")).toBeInTheDocument();
    expect(within(question).getAllByRole("link", { name: "https://example.com/source" })).toHaveLength(2);
    expect(within(screen.getByRole("region", { name: "Limitations" })).getByText("片段绑定不证明结论真实")).toBeInTheDocument();
  });

  it("navigates every directory item by keyboard and repeats focus and scroll for the same question", async () => {
    const originalScroll = HTMLElement.prototype.scrollIntoView;
    const scroll = vi.fn();
    HTMLElement.prototype.scrollIntoView = scroll;
    try {
      const user = userEvent.setup();
      render(<ResearchFindingsReader language="en" findings={parseResearchFindings(findingsResponse(), "run_structured")} />);
      const directory = screen.getByRole("navigation", { name: "Question directory" });
      const buttons = within(directory).getAllByRole("button");
      buttons[0].focus();
      await user.tab();
      expect(buttons[1]).toHaveFocus();
      await user.keyboard("{Enter}");
      expect(screen.getByRole("region", { name: "未解决问题" })).toHaveFocus();
      expect(buttons[1]).toHaveAttribute("aria-current", "location");
      expect(within(screen.getByRole("region", { name: "未解决问题" })).getByText("证据不足")).toBeInTheDocument();
      expect(scroll).toHaveBeenCalledWith({ block: "start", behavior: "auto" });
      const before = scroll.mock.calls.length;
      buttons[1].focus(); await user.keyboard("{Enter}");
      expect(screen.getByRole("region", { name: "未解决问题" })).toHaveFocus();
      expect(scroll).toHaveBeenCalledTimes(before + 1);
      buttons[0].focus(); await user.keyboard(" ");
      expect(screen.getByRole("region", { name: "研究问题" })).toHaveFocus();
      expect(buttons[0]).toHaveAttribute("aria-current", "location");
      expect(buttons[1]).not.toHaveAttribute("aria-current");
      await user.tab();
      expect(screen.getByRole("link", { name: "https://example.com/source" })).toHaveFocus();
    } finally {
      if (originalScroll) HTMLElement.prototype.scrollIntoView = originalScroll;
      else Reflect.deleteProperty(HTMLElement.prototype, "scrollIntoView");
    }
  });

  it("clears question selection and source inspection when a different report run reuses IDs", async () => {
    const user = userEvent.setup();
    const first = parseResearchFindings(findingsResponse(), "run_structured");
    const { rerender } = render(<ResearchFindingsReader language="en" findings={first} />);
    await user.click(within(screen.getByRole("navigation", { name: "Question directory" })).getAllByRole("button")[0]);
    await user.click(screen.getByRole("button", { name: "Inspect full persisted snippet" }));
    expect(screen.getByRole("region", { name: "Full persisted snippet" })).toBeInTheDocument();
    const next = findingsResponse("run_next");
    next.report.questions[0].text = "Next accepted question";
    next.report.findings[0].statement = "Next observed candidate";
    next.artifact.content = JSON.stringify(next.report);
    rerender(<ResearchFindingsReader language="en" findings={parseResearchFindings(next, "run_next")} />);
    expect(screen.queryByRole("region", { name: "Full persisted snippet" })).not.toBeInTheDocument();
    expect(screen.queryByText("来源绑定的候选结论")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "研究问题" })).not.toBeInTheDocument();
    expect(within(screen.getByRole("navigation", { name: "Question directory" })).getAllByRole("button").every((button) => !button.hasAttribute("aria-current"))).toBe(true);
    expect(within(screen.getByRole("region", { name: "Next accepted question" })).getByText("Next observed candidate")).toBeInTheDocument();
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
      value.report.questions[0].text = "Accepted long question 😀e\u0301\n".repeat(60);
      value.report.findings[0].statement = "Candidate long Unicode statement 😀e\u0301\n".repeat(30);
      ref.excerpt = "长引用😀e\u0301".repeat(100);
      ref.excerpt_start = 1;
      ref.excerpt_end = 1 + Array.from(ref.excerpt).length;
      ref.snippet = "前" + ref.excerpt + "后";
      ref.snippet += "余😀".repeat(4000);
      value.artifact.content = JSON.stringify(value.report);
      const user = userEvent.setup();
      render(<ResearchFindingsReader language="en" findings={parseResearchFindings(value, "run_structured")} />);
      expect(screen.getByRole("heading", { name: /Accepted long question/ }).textContent).toBe(value.report.questions[0].text);
      expect(screen.getByText(value.report.findings[0].statement, { normalizer: (text) => text }).textContent).toBe(value.report.findings[0].statement);
      expect(screen.getByText(ref.excerpt).textContent).toBe(ref.excerpt);
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
