import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("offline Decision Research Agent showcase", () => {
  it("uses the product name and a concise report-focused subtitle in the header", () => {
    render(<App showcaseState="overview" />);

    expect(screen.getByRole("heading", { name: "Decision Research Agent" })).toBeInTheDocument();
    expect(screen.getByText("从研究问题到可复核的报告")).toBeInTheDocument();
    expect(screen.queryByText("Agent-first / human-governed / Evidence-governed")).not.toBeInTheDocument();
  });

  it("focuses the conclusion and comparison section from its report shortcut", async () => {
    const user = userEvent.setup();
    const previousScrollIntoView = HTMLElement.prototype.scrollIntoView;
    const scrollTargets: string[] = [];
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: function (this: HTMLElement) {
        scrollTargets.push(this.id);
      }
    });

    try {
      render(<App showcaseState="overview" />);
      const navigation = screen.getByRole("navigation", { name: "浏览报告" });
      await user.click(within(navigation).getByRole("button", { name: "结论与比较" }));

      const section = document.getElementById("conclusion-section");
      expect(document.activeElement).toBe(section);
      expect(scrollTargets).toContain("conclusion-section");
    } finally {
      if (previousScrollIntoView) {
        Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
          configurable: true,
          value: previousScrollIntoView
        });
      } else {
        delete (HTMLElement.prototype as Partial<HTMLElement>).scrollIntoView;
      }
    }
  });

  it("focuses and scrolls to the selected source from its evidence shortcut", async () => {
    const user = userEvent.setup();
    const previousWidth = window.innerWidth;
    const previousScrollIntoView = HTMLElement.prototype.scrollIntoView;
    const scrollTargets: string[] = [];
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: function (this: HTMLElement) {
        scrollTargets.push(this.id);
      }
    });

    try {
      render(<App showcaseState="overview" />);
      const navigation = screen.getByRole("navigation", { name: "浏览报告" });
      await user.click(within(navigation).getByRole("button", { name: "查看依据" }));

      expect(document.activeElement).toBe(document.getElementById("evidence-detail"));
      expect(scrollTargets).toContain("evidence-detail");
    } finally {
      Object.defineProperty(window, "innerWidth", { configurable: true, value: previousWidth });
      if (previousScrollIntoView) {
        Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
          configurable: true,
          value: previousScrollIntoView
        });
      } else {
        delete (HTMLElement.prototype as Partial<HTMLElement>).scrollIntoView;
      }
    }
  });

  it("opens and focuses the complete report from its report shortcut", async () => {
    const user = userEvent.setup();
    render(<App showcaseState="overview" />);

    const navigation = screen.getByRole("navigation", { name: "浏览报告" });
    await user.click(within(navigation).getByRole("button", { name: "阅读完整报告" }));

    expect(document.getElementById("full-report-disclosure")).toHaveAttribute("open");
    expect(document.activeElement).toBe(document.getElementById("full-report-content"));
  });

  it("opens the evidence route on its second linked claim and source", () => {
    render(<App showcaseState="evidence" />);

    const sourcePanel = screen.getByRole("region", { name: "相关资料" });
    expect(screen.getByText("对应结论")).toBeInTheDocument();
    const systemAccessSource = within(sourcePanel).getByRole("button", { name: /系统接入清单/ });
    expect(systemAccessSource).toHaveAttribute("aria-pressed", "true");
    expect(document.getElementById("research-claim-claim_refund_write_unconfirmed")).toHaveClass("selected");
    expect(document.getElementById("research-claim-claim_bounded_assistant")).not.toHaveClass("selected");
  });

  it("keeps internal Evidence IDs out of the source picker and supported finding", async () => {
    const user = userEvent.setup();
    render(<App showcaseState="overview" />);

    const sourcePanel = screen.getByRole("region", { name: "相关资料" });
    const pilotSource = within(sourcePanel).getByRole("button", { name: /试点需求记录/ });
    expect(pilotSource).not.toHaveTextContent("ev_pilot_scope");

    await user.click(pilotSource);

    expect(sourcePanel.querySelector(".source-claim-heading")).not.toHaveTextContent("claim_bounded_assistant");
    expect(sourcePanel).toHaveTextContent("试点先覆盖政策检索与答复草稿，发送前仍需客服审核。");
  });

  it("scrolls to source details on a narrow screen and back to the referring finding", async () => {
    const user = userEvent.setup();
    const previousWidth = window.innerWidth;
    const previousScrollIntoView = HTMLElement.prototype.scrollIntoView;
    const scrollTargets: string[] = [];
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: function (this: HTMLElement) {
        scrollTargets.push(this.id);
      }
    });

    try {
      render(<App showcaseState="overview" />);
      const finding = document.getElementById("research-claim-claim_refund_write_unconfirmed");
      expect(finding).not.toBeNull();
      await user.click(within(finding as HTMLElement).getByRole("button", { name: "查看依据" }));

      await waitFor(() => {
        expect(document.activeElement).toBe(document.getElementById("evidence-detail"));
      });
      expect(scrollTargets).toContain("evidence-detail");

      await user.click(screen.getByRole("button", { name: "返回相关结论" }));
      expect(scrollTargets).toContain("research-claim-claim_refund_write_unconfirmed");
    } finally {
      Object.defineProperty(window, "innerWidth", { configurable: true, value: previousWidth });
      if (previousScrollIntoView) {
        Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
          configurable: true,
          value: previousScrollIntoView
        });
      } else {
        delete (HTMLElement.prototype as Partial<HTMLElement>).scrollIntoView;
      }
    }
  });

  it("repeats focus and scroll when the same finding is opened or returned to again", async () => {
    const user = userEvent.setup();
    const previousScrollIntoView = HTMLElement.prototype.scrollIntoView;
    const scrollTargets: string[] = [];
    Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
      configurable: true,
      value: function (this: HTMLElement) {
        scrollTargets.push(this.id);
      }
    });

    try {
      render(<App showcaseState="overview" />);
      const finding = document.getElementById("research-claim-claim_refund_write_unconfirmed");
      expect(finding).not.toBeNull();
      const inspect = within(finding as HTMLElement).getByRole("button", { name: "查看依据" });

      await user.click(inspect);
      await user.click(inspect);
      expect(scrollTargets.filter((id) => id === "evidence-detail")).toHaveLength(2);

      const returnToClaim = screen.getByRole("button", { name: "返回相关结论" });
      await user.click(returnToClaim);
      await user.click(returnToClaim);
      expect(scrollTargets.filter((id) => id === "research-claim-claim_refund_write_unconfirmed"))
        .toHaveLength(2);
    } finally {
      if (previousScrollIntoView) {
        Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
          configurable: true,
          value: previousScrollIntoView
        });
      } else {
        delete (HTMLElement.prototype as Partial<HTMLElement>).scrollIntoView;
      }
    }
  });

  it("keeps blocked cases free of full-report navigation and result controls", () => {
    render(<App showcaseState="blocked" />);

    expect(screen.getAllByText("政策资料访问尚未确认，当前运行未交付报告。").length).toBeGreaterThan(1);
    expect(screen.getByText("先确认已批准的政策资料和退款规则访问权限，再由人工决定是否扩大试点。")).toBeInTheDocument();
    expect(screen.queryByRole("navigation", { name: "浏览报告" })).not.toBeInTheDocument();
    expect(document.querySelector(".brief-reader-disclosure")).not.toBeInTheDocument();
    expect(document.querySelector(".result-reader")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "下载报告" })).not.toBeInTheDocument();
  });

  it("renders the six operator screens inside the collapsed technical console", async () => {
    const user = userEvent.setup();
    render(<App showcaseState="overview" />);

    const technicalConsole = document.querySelector(".technical-console-view");
    expect(technicalConsole).not.toHaveAttribute("open");
    await user.click(within(technicalConsole as HTMLElement).getByText("运行与诊断"));

    const navigation = screen.getByRole("navigation", {
      name: /demo console screens/i
    });

    [
      "Command Center",
      "Run Lifecycle",
      "Evidence Ledger",
      "Review / Verification",
      "Canonical Result",
      "Architecture Explain Mode"
    ].forEach((screenName) => {
      expect(within(navigation).getByRole("button", { name: screenName })).toBeInTheDocument();
    });
  });

  it("keeps the overview focused on the brief with technical details collapsed", () => {
    render(<App showcaseState="overview" />);

    expect(screen.getByRole("heading", { name: "客服团队应该先试点内部知识助手，还是直接让 Agent 自动处理退款？" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "先试点内部知识助手" })).toBeInTheDocument();
    expect(document.querySelector(".stage-rail")).toBeNull();
    expect(document.querySelector(".technical-console-view")).not.toHaveAttribute("open");
    expect(document.querySelector(".technical-live-view")).toBeNull();
    expect(document.querySelector(".inspector-technical")).not.toHaveAttribute("open");
    expect(document.querySelector(".brief-reader-disclosure")).not.toHaveAttribute("open");
    expect(screen.getByText("完整报告")).toBeInTheDocument();
  });

  it("keeps the mobile example compact while retaining the question and recommendation", () => {
    const previousWidth = window.innerWidth;
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 390 });
    try {
      render(<App showcaseState="overview" />);

      expect(document.querySelector(".stage-rail-menu")).not.toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "客服团队应该先试点内部知识助手，还是直接让 Agent 自动处理退款？" })).toBeInTheDocument();
      expect(screen.getByRole("heading", { name: "先试点内部知识助手" })).toBeInTheDocument();
    } finally {
      Object.defineProperty(window, "innerWidth", { configurable: true, value: previousWidth });
    }
  });

  it("defaults to Chinese and can switch to English", async () => {
    const user = userEvent.setup();
    render(<App showcaseState="overview" />);

    expect(screen.getByRole("heading", { name: "Decision Research Agent" })).toBeInTheDocument();
    expect(screen.getByText("从研究问题到可复核的报告")).toBeInTheDocument();
    expect(screen.getByText("运行与诊断")).toBeInTheDocument();
    expect(screen.getByText("复核状态：已通过；依据核验单独记录。")).toBeInTheDocument();
    expect(
      screen.getAllByText("本案例使用合成资料，不代表真实客户试点或实际业务成效；节省时间和采用率仍待实测。")
    ).toHaveLength(1);
    expect(screen.queryByText(/只读控制台/)).not.toBeInTheDocument();
    expect(screen.queryByText("Agent-first / human-governed / Evidence-governed")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "English" }));

    expect(screen.getByRole("heading", { name: "Decision Research Agent" })).toBeInTheDocument();
    expect(screen.getByText("From research question to a reviewable report")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Report navigation" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View supporting evidence" })).toBeInTheDocument();
    expect(screen.getByText("Runtime & diagnostics")).toBeInTheDocument();
    expect(screen.getByText("Review status: approved; source verification is recorded separately.")).toBeInTheDocument();
    expect(screen.queryByText(/read-only operator console/i)).not.toBeInTheDocument();
  });

  it("keeps the document language aligned with the language toggle", async () => {
    const user = userEvent.setup();
    render(<App showcaseState="overview" />);

    expect(document.documentElement).toHaveAttribute("lang", "zh-CN");

    await user.click(screen.getByRole("button", { name: "English" }));
    expect(document.documentElement).toHaveAttribute("lang", "en");

    await user.click(screen.getByRole("button", { name: "中文" }));
    expect(document.documentElement).toHaveAttribute("lang", "zh-CN");
  });

  it("states that the UI starts runs without owning authority", async () => {
    const user = userEvent.setup();
    render(<App showcaseState="overview" />);

    await user.click(screen.getByRole("button", { name: "English" }));
    await user.click(screen.getByText("Runtime & diagnostics"));
    await user.click(screen.getByRole("button", { name: "Architecture Explain Mode" }));

    expect(screen.getByText(/UI starts runs and consumes public contracts without owning authority/)).toBeInTheDocument();
    expect(screen.queryByText(/only observes public contracts/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/read-only/i)).not.toBeInTheDocument();
  });

  it("does not expose chat input or message bubble as the primary interaction", () => {
    render(<App showcaseState="overview" />);

    expect(screen.queryByPlaceholderText(/message|chat|输入消息|聊天/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /message|chat|输入消息|聊天/i })).not.toBeInTheDocument();
    expect(document.querySelector(".chat-bubble")).not.toBeInTheDocument();
  });

  it("keeps the report and source panel primary while moving screen navigation into technical details", async () => {
    const user = userEvent.setup();
    render(<App showcaseState="overview" />);

    expect(screen.queryByRole("navigation", { name: "Research flow" })).not.toBeInTheDocument();
    expect(document.querySelector(".stage-rail")).not.toBeInTheDocument();
    expect(document.querySelector(".research-work-surface")).toBeInTheDocument();
    expect(document.querySelector(".judgment-sidebar")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "浏览报告" })).toBeInTheDocument();

    const technicalDisclosure = screen.getByText("运行与诊断").closest("details");
    expect(technicalDisclosure).toBeInTheDocument();
    expect(technicalDisclosure).not.toHaveAttribute("open");
    expect(document.querySelector(".stage-rail")).toBeNull();
    await user.click(screen.getByText("运行与诊断"));
    const technicalNavigation = screen.getByRole("navigation", { name: "Demo console screens" });
    expect(within(technicalNavigation).getByRole("button", { name: "Command Center" })).toBeInTheDocument();
  });

  it("renders the Evidence review showcase with claim and source judgment", () => {
    render(<App showcaseState="evidence" />);

    const sourcePanel = screen.getByRole("region", { name: "相关资料" });
    expect(within(sourcePanel).getByRole("button", { name: /系统接入清单/ })).toHaveAttribute("aria-pressed", "true");
    expect(document.getElementById("research-claim-claim_refund_write_unconfirmed")).toHaveClass("selected");
    expect(screen.getByText("所选资料支持第二条结论：生产环境退款写入尚未获批准或验证。"))
      .toBeInTheDocument();
    expect(sourcePanel.querySelector(".source-technical")).not.toHaveAttribute("open");
    expect(screen.getByText("完整报告")).toBeInTheDocument();
    expect(screen.queryByText("核验后再交付")).not.toBeInTheDocument();
    expect(screen.queryByText("before delivery")).not.toBeInTheDocument();
  });

  it("links a claim to its exact source excerpt and returns focus to the claim", async () => {
    const user = userEvent.setup();
    render(<App showcaseState="overview" />);

    const finding = document.getElementById("research-claim-claim_refund_write_unconfirmed");
    expect(finding).not.toBeNull();
    await user.click(within(finding as HTMLElement).getByRole("button", { name: "查看依据" }));

    await waitFor(() => {
      expect(document.activeElement).toBe(document.getElementById("evidence-detail"));
    });
    expect(screen.getAllByText("生产环境退款写入集成尚未获批准或验证。").length).toBeGreaterThan(1);
    expect(screen.getAllByText("退款写入接入尚未被批准或验证，因此不能承诺 Agent 自动退款。").length).toBeGreaterThan(1);

    await user.click(screen.getByRole("button", { name: "返回相关结论" }));

    await waitFor(() => {
      expect(document.activeElement).toBe(
        document.getElementById("research-claim-claim_refund_write_unconfirmed")
      );
    });
  });

  it("shows the selected source claim when a source is chosen directly", async () => {
    const user = userEvent.setup();
    render(<App showcaseState="overview" />);

    await user.click(screen.getByRole("button", { name: /系统接入清单/ }));

    expect(screen.getAllByText("退款写入接入尚未被批准或验证，因此不能承诺 Agent 自动退款。").length).toBeGreaterThan(1);
    expect(screen.getAllByText("生产环境退款写入集成尚未获批准或验证。").length).toBeGreaterThan(1);
    expect(screen.queryByText("尚未关联支持结论。")).not.toBeInTheDocument();
  });

  it("keeps blocked runs visibly unreviewed and without report actions", () => {
    render(<App showcaseState="blocked" />);

    expect(screen.getByText("本次运行未交付报告")).toBeInTheDocument();
    expect(screen.getByText("等待人工确认")).toBeInTheDocument();
    expect(screen.getAllByText("未交付").length).toBeGreaterThan(1);
    expect(screen.getAllByText("政策资料访问尚未确认，当前运行未交付报告。").length).toBeGreaterThan(1);
    expect(screen.queryByRole("navigation", { name: "浏览报告" })).not.toBeInTheDocument();
    expect(screen.queryByText("完整报告")).not.toBeInTheDocument();
    expect(screen.queryByText("研究报告")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "下载报告" })).not.toBeInTheDocument();
    expect(screen.queryByText("Canonical Decision Brief")).not.toBeInTheDocument();
  });

  it("renders the blocked diagnostic chain without calling the first failure a proven root cause", async () => {
    const user = userEvent.setup();
    render(<App showcaseState="blocked" />);

    const diagnosticCard = screen.getByText("诊断链").closest("details");
    expect(diagnosticCard).not.toHaveAttribute("open");
    await user.click(screen.getByText("诊断链"));

    expect(screen.getByText("首个显示失败步骤")).toBeInTheDocument();
    expect(screen.getByText("tool_failed", { exact: true })).toBeInTheDocument();
    expect(screen.getByText("持久化终态原因")).toBeInTheDocument();
    expect(screen.getByText("execution / execution_error")).toBeInTheDocument();
    expect(screen.getByText("既有处置")).toBeInTheDocument();
    expect(screen.getByText("review_required / not_delivered")).toBeInTheDocument();
    expect(
      screen.getByText("这是生命周期中首先显示为失败的步骤，不等同于已证明的根因。")
    ).toBeInTheDocument();
    expect(screen.getByText("既有处置")).toBeInTheDocument();
    expect(screen.queryByText("下一步需要澄清")).not.toBeInTheDocument();
    expect(screen.getByText("先确认已批准的政策资料和退款规则访问权限，再由人工决定是否扩大试点。"))
      .toBeInTheDocument();
    expect(screen.queryByText(/请修正.*后再次 review/)).not.toBeInTheDocument();
    expect(screen.queryByText(/先完成 Evidence review/)).not.toBeInTheDocument();
    expect(screen.queryByText(/raw_error|provider|exception|\/private\//i)).not.toBeInTheDocument();
    expect(diagnosticCard).toBeInTheDocument();
    expect(diagnosticCard?.closest(".blocked-showcase")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "English" }));

    expect(screen.getByText("First displayed failing step")).toBeInTheDocument();
    expect(screen.getByText("The first displayed failing step is not a proven root cause.")).toBeInTheDocument();
    expect(screen.getByText("Durable terminal cause")).toBeInTheDocument();
    expect(screen.getByText("Disposition")).toBeInTheDocument();
    expect(screen.getAllByText("Human confirmation needed").length).toBeGreaterThan(1);
    expect(screen.getByText("Confirm access to the approved policy material and refund rules, then have a person decide whether to expand the pilot."))
      .toBeInTheDocument();
    expect(screen.queryByText(/Correct the Evidence or tool result, then review again/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Complete Evidence review before producing a canonical result/i)).not.toBeInTheDocument();
  });

  it("localizes showcase state labels in both locales", async () => {
    const user = userEvent.setup();
    render(<App showcaseState="overview" />);

    const reportNavigation = screen.getByRole("navigation", { name: "浏览报告" });
    expect(within(reportNavigation).getByRole("button", { name: "结论与比较" })).toBeInTheDocument();
    expect(within(reportNavigation).getByRole("button", { name: "查看依据" })).toBeInTheDocument();
    expect(screen.getByText("报告已交付")).toBeInTheDocument();
    expect(screen.getByText("先试点内部知识助手")).toBeInTheDocument();
    expect(screen.getAllByText("已纳入案例").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "English" }));

    const englishNavigation = screen.getByRole("navigation", { name: "Report navigation" });
    expect(within(englishNavigation).getByRole("button", { name: "Conclusion and comparison" }))
      .toBeInTheDocument();
    expect(within(englishNavigation).getByRole("button", { name: "View supporting evidence" }))
      .toBeInTheDocument();
    expect(screen.getByText("Report delivered")).toBeInTheDocument();
    expect(screen.getByText("先试点内部知识助手")).toBeInTheDocument();
    expect(screen.getAllByText("Included in this case").length).toBeGreaterThan(0);
  });

  it("keeps the comparison heading concise and omits the internal evidence counter", () => {
    render(<App showcaseState="overview" />);

    const comparisonHeading = screen.getByRole("heading", { name: "比较方案" });
    expect(comparisonHeading.parentElement?.querySelector(".step-stage")).toBeNull();

    const sourcePanel = screen.getByRole("region", { name: "相关资料" });
    expect(within(sourcePanel).getByText("选择资料，查看它支持的结论、摘录和全文。")).toBeInTheDocument();
    expect(within(sourcePanel).queryByText("Evidence refs", { exact: true })).not.toBeInTheDocument();
  });

  it("keeps the delivered evidence review in one historical time frame in English", async () => {
    const user = userEvent.setup();
    render(<App showcaseState="evidence" />);

    await user.click(screen.getByRole("button", { name: "English" }));

    expect(
      screen.getAllByText("This case uses synthetic material and does not represent a customer trial or measured business impact; time savings and adoption remain unmeasured.")
    ).toHaveLength(1);
    expect(screen.getByText("Linked finding")).toBeInTheDocument();
    expect(screen.getByText("Report delivered")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Read the full report" })).toBeInTheDocument();
    expect(screen.queryByText("Deliver after judgment")).not.toBeInTheDocument();
    expect(screen.queryByText("before delivery")).not.toBeInTheDocument();
  });

  it("lets each definition row span the parent grid and own its two-column layout", () => {
    const process = (
      globalThis as typeof globalThis & {
        process: {
          cwd(): string;
          getBuiltinModule(name: "fs"): {
            readFileSync(path: string, encoding: "utf8"): string;
          };
        };
      }
    ).process;
    const styles = process
      .getBuiltinModule("fs")
      .readFileSync(`${process.cwd()}/src/styles.css`, "utf8");
    const definitionRowRule = styles.match(/\.definition-row\s*\{([^}]*)\}/)?.[1];

    expect(definitionRowRule).toBeDefined();
    expect(definitionRowRule).toMatch(/grid-column:\s*1\s*\/\s*-1/);
    expect(definitionRowRule).toMatch(/display:\s*grid/);
    expect(definitionRowRule).toMatch(
      /grid-template-columns:\s*minmax\(120px,\s*0\.45fr\)\s+minmax\(0,\s*1fr\)/
    );
  });

  it("shows static demo data for lifecycle, evidence, review, verification, and result", async () => {
    const user = userEvent.setup();
    render(<App showcaseState="overview" />);

    expect(screen.getAllByText("run_demo_support_refund_normal").length).toBeGreaterThan(0);

    await user.click(screen.getByText("运行与诊断"));
    await user.click(screen.getByRole("button", { name: "Run Lifecycle" }));
    expect(screen.getAllByText(/evidence_frozen/).length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Evidence Ledger" }));
    expect(screen.getAllByText(/ev_pilot_scope/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/claim_bounded_assistant/).length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Review / Verification" }));
    expect(screen.getAllByText("approved").length).toBeGreaterThan(0);
    expect(screen.getAllByText("verified").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Canonical Result" }));
    expect(screen.getAllByText("customer-support-refund-pilot-decision-brief.md").length).toBeGreaterThan(0);
    expect(screen.getByText(/python tools\/decision_research_agent_tool.py run/)).toBeInTheDocument();
  });

  it("renders the CLI golden path without diff markers", () => {
    render(<App showcaseState="overview" />);

    const snippet = document.querySelector(".inspector-panel.dark pre");

    expect(snippet).toHaveTextContent('--query "Compare the evidence behind the proposed decision"');
    expect(snippet?.textContent).not.toMatch(/^\+\s/m);
  });

  it.each(["overview", "evidence", "blocked"])("opens the explicit %s example without contacting the service", (scenario) => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const previousUrl = window.location.href;
    try {
      window.history.replaceState({}, "", `/?showcase=${scenario}`);
      render(<App />);
      expect(screen.getByRole("heading", { name: "Decision Research Agent" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "开始研究" })).not.toBeInTheDocument();
      expect(fetch).not.toHaveBeenCalled();
    } finally {
      window.history.replaceState({}, "", previousUrl);
    }
  });
});
