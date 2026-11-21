import type { ReactNode } from "react";
import type { Language } from "../i18n";

const modules = ["compare", "source", "follow"] as const;
type HomeAction = typeof modules[number] | "outline";

const homeCopy = {
  zh: {
    title: "你想研究什么",
    questionMark: "？",
    description: "把公开资料整理成带引用的研究报告。可以比较方案、核对原文，继续追问证据不足的地方。",
    outline: "看看报告如何引用原文",
    currentSources: "查看本次引用",
    unresolved: (count: number) => `${count} 项待查`,
    unresolvedUnread: "待查项在读到报告后显示",
    generalReport: "阅读本次报告",
    unresolvedUnavailable: "通用报告仅显示正文",
    tools: "研究工具",
    compare: ["多问题比较", "在同一份报告中逐项对照"],
    source: ["核对结论出处", "从一条结论回到引用原文"],
    follow: ["跟进未解问题"]
  },
  en: {
    title: "What do you want to research",
    questionMark: "?",
    description: "Turn public sources into a cited research report. Compare options, check original passages, and follow up where evidence is missing.",
    outline: "How reports cite sources",
    currentSources: "View citations for this run",
    unresolved: (count: number) => `${count} open ${count === 1 ? "question" : "questions"}`,
    unresolvedUnread: "Open questions appear once the report is available",
    generalReport: "Read this report",
    unresolvedUnavailable: "General reports contain report text only",
    tools: "Research tools",
    compare: ["Compare questions", "Compare findings side by side in one report"],
    source: ["Check sources", "Trace a finding back to its cited passage"],
    follow: ["Follow up"]
  }
};

export function WorkspaceHome({ language, hasReport, unresolvedCount, onOpen, children }: {
  language: Language;
  hasReport: boolean;
  unresolvedCount?: number;
  onOpen: (name: HomeAction, trigger: HTMLElement) => void;
  children: ReactNode;
}) {
  const t = homeCopy[language];
  const outlineLabel = unresolvedCount !== undefined ? t.currentSources : hasReport ? t.generalReport : t.outline;
  const followDescription = unresolvedCount !== undefined ? t.unresolved(unresolvedCount)
    : hasReport ? t.unresolvedUnavailable : t.unresolvedUnread;
  return <main id="dw-home" className="dw-home" lang={language === "zh" ? "zh-CN" : "en"}>
    <section className="dw-home-hero" aria-labelledby="dw-home-title">
      <div className="dw-home-intro">
        <h1 id="dw-home-title">{t.title}<span>{t.questionMark}</span></h1>
        <p>{t.description}</p>
        {children}
      </div>
      <figure className="dw-paper-art">
        <img src={`${import.meta.env.BASE_URL}paper-relief.jpg`} alt="" width={1448} height={1086} fetchPriority="high" />
        <button type="button" className="dw-paper-outline" onClick={(event) => onOpen("outline", event.currentTarget)}>
          {outlineLabel} <span aria-hidden="true">→</span>
        </button>
      </figure>
    </section>
    <section className="dw-home-tools" aria-labelledby="dw-home-tools-title">
      <h2 id="dw-home-tools-title">{t.tools}</h2>
      <ul className="dw-module-grid">
        {modules.map((name) => {
          const [title, description] = t[name];
          return <li key={name}>
            <button type="button" className="dw-module-card" data-module={name}
              aria-labelledby={`dw-module-${name}-title`}
              aria-describedby={`dw-module-${name}-description`}
              onClick={(event) => onOpen(name, event.currentTarget)}>
              <strong className="dw-module-title" id={`dw-module-${name}-title`}>{title}</strong>
              <span className="dw-module-description" id={`dw-module-${name}-description`}>{name === "follow" ? followDescription : description}</span>
              <span className="dw-module-action" aria-hidden="true">→</span>
            </button>
          </li>;
        })}
      </ul>
    </section>
  </main>;
}
