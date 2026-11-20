import type { ReactNode } from "react";
import type { Language } from "../i18n";

const modules = ["compare", "source", "follow"] as const;
const glyphs = { compare: "≋", source: "“", follow: "↳" };

const homeCopy = {
  zh: {
    title: "把公开资料整理成",
    titleAccent: "有出处的研究报告。",
    description: "围绕你的问题检索资料，逐项给出结论。你可以回看引用原文，也可以继续追问证据不足的地方。",
    origin: "来源原文",
    conclusion: "报告结论",
    tools: "研究工具",
    compare: ["多问题比较", "把同一决策拆成几个问题，在一份报告里逐项对照。", "编排问题"],
    source: ["核对结论出处", "从报告的一条结论，找到支持它的原文和来源。", "查看依据"],
    follow: ["跟进未解问题", "从报告留下的疑问开始，决定下一次研究的范围。", "选择待查项"]
  },
  en: {
    title: "From public sources to",
    titleAccent: "cited research reports.",
    description: "Get findings for each question, read the original cited passages, and follow up where evidence is missing.",
    origin: "Source passage",
    conclusion: "Report finding",
    tools: "Research tools",
    compare: ["Compare questions", "Break a decision into several questions and compare the findings in one report.", "Arrange questions"],
    source: ["Check sources", "Find the original passage and source behind a finding in your report.", "View evidence"],
    follow: ["Follow up", "Use the open questions in your report to scope your next round of research.", "Select open questions"]
  }
};

export function WorkspaceHome({ language, onOpen, children }: {
  language: Language;
  onOpen: (name: typeof modules[number], trigger: HTMLElement) => void;
  children: ReactNode;
}) {
  const t = homeCopy[language];
  return <main className="dw-home" lang={language === "zh" ? "zh-CN" : "en"}>
    <section className="dw-home-hero" aria-labelledby="dw-home-title">
      <div className="dw-home-intro">
        <h1 id="dw-home-title">{t.title}<br /> <span>{t.titleAccent}</span></h1>
        <p>{t.description}</p>
        <div className="dw-home-diagram" aria-hidden="true">
          <span className="dw-home-folio"><span className="dw-folio-lines"><i /><i /><i /></span>{t.origin}</span>
          <span className="dw-folio-arrow" />
          <span className="dw-home-folio"><span className="dw-folio-lines"><i /><i /></span>{t.conclusion}</span>
        </div>
      </div>
      {children}
    </section>
    <section className="dw-home-tools" aria-labelledby="dw-home-tools-title">
      <h2 id="dw-home-tools-title">{t.tools}</h2>
      <div className="dw-module-grid">
        {modules.map((name) => {
          const [title, description, action] = t[name];
          return <button key={name} type="button" className="dw-module-card" data-module={name}
            aria-labelledby={`dw-module-${name}-title dw-module-${name}-action`}
            aria-describedby={`dw-module-${name}-description`}
            onClick={(event) => onOpen(name, event.currentTarget)}>
            <span className="dw-module-title">
              <span className="dw-module-glyph" aria-hidden="true">{glyphs[name]}</span>
              <strong id={`dw-module-${name}-title`}>{title}</strong>
            </span>
            <span className="dw-module-description" id={`dw-module-${name}-description`}>{description}</span>
            <span className="dw-module-action" id={`dw-module-${name}-action`}>{action} <span aria-hidden="true">↗</span></span>
          </button>;
        })}
      </div>
    </section>
  </main>;
}
