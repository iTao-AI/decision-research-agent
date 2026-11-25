import { useEffect, useId, useLayoutEffect, useRef, useState, type Ref } from "react";
import { copy, type Language } from "../i18n";
import type { BoundFinding, BoundSourceReference, ResearchFindingsReport, ResearchFindingsResponse } from "../researchFindings";
import type { RunEvidenceProjection } from "../runProjection";
import { safeHttpUrl } from "./resultReader";

export type UnresolvedQuestionControls = {
  selectedQuestionIds: readonly string[];
  disabled: boolean;
  onToggleQuestion: (questionId: string) => void;
  onPrepare: () => void;
  prepareButtonRef: Ref<HTMLButtonElement>;
};

export type WorkspaceReportView = "report" | "sources" | "unresolved";

type FollowQuestion = (questionId: string, trigger: HTMLElement) => void;

const readerCopy = {
  zh: {
    findings: "研究结论",
    question: "查看完整问题",
    unresolved: "待查问题",
    unresolvedCount: (count: number) => `待查 ${count} 项`,
    noUnresolved: "这份报告没有待查问题。",
    continueResearch: "继续研究",
    citations: (count: number, sources: number) => `${count} 处引用 · ${sources} 份来源`,
    conditions: "适用条件与限制",
    contradictions: "报告中的矛盾记录",
    noContradictions: "报告未列出矛盾。",
    binding: "引文定位到本次保存的摘录。资料的核实状态另有记录。",
    location: (number: number) => `引文 ${number}`,
    revision: "Git 分支或标签",
    commit: "提交版本",
    located: "已定位原句",
    verified: "服务记录为已核实",
    unverified: "独立核实未确认",
    unknown: "核实状态未提供",
    inspect: "展开已保存的摘录",
    saved: "已保存的摘录",
    excerpt: "引用原句",
    openSource: "打开来源网页",
    returnToCitation: "返回引用处"
  },
  en: {
    findings: "Findings",
    question: "View full question",
    unresolved: "Open questions",
    unresolvedCount: (count: number) => `${count} open ${count === 1 ? "question" : "questions"}`,
    noUnresolved: "This report has no open questions.",
    continueResearch: "Continue research",
    citations: (count: number, sources: number) => `${count} ${count === 1 ? "citation" : "citations"} · ${sources} ${sources === 1 ? "source" : "sources"}`,
    conditions: "Conditions and limitations",
    contradictions: "Contradictions recorded in the report",
    noContradictions: "The report lists no contradictions.",
    binding: "Citations point to passages saved during this run. Verification is recorded separately.",
    location: (number: number) => `Citation ${number}`,
    revision: "Git ref",
    commit: "Commit",
    located: "Passage located",
    verified: "Recorded as verified by the service",
    unverified: "Independent verification unconfirmed",
    unknown: "Verification status unavailable",
    inspect: "Expand saved excerpt",
    saved: "Saved excerpt",
    excerpt: "Cited passage",
    openSource: "Open source webpage",
    returnToCitation: "Return to citation"
  }
};

export function ResearchFindingsReader({ language, documentLanguage, findings, followUp, variant, initialView = "report", evidence, onFollowQuestion }: {
  language: Language;
  documentLanguage?: Language;
  findings: ResearchFindingsResponse;
  followUp?: UnresolvedQuestionControls;
  variant?: "workspace";
  initialView?: WorkspaceReportView;
  evidence?: readonly RunEvidenceProjection[];
  onFollowQuestion?: FollowQuestion;
}) {
  const t = copy[language].research;
  const report = findings.report;
  const reportKey = `${report.run_id}/${report.profile_id}@${report.profile_version}/${findings.artifact.content_hash}`;
  const selection = followUp && <section className="research-follow-up-controls" aria-label={t.followUp.selectionTitle}>
    <h3>{t.followUp.selectionTitle}</h3><p>{t.followUp.selectionHint}</p>
    <button type="button" ref={followUp.prepareButtonRef} disabled={followUp.disabled || !followUp.selectedQuestionIds.length}
      onClick={followUp.onPrepare}>{t.followUp.prepare}</button>
  </section>;

  if (variant) {
    const labels = readerCopy[documentLanguage ?? language];
    const reportLang = documentLanguage === "zh" ? "zh-CN" : documentLanguage;
    return <article className="research-findings-reader dw-findings-reader" aria-label={t.title}>
      <WorkspaceQuestionReport key={`${reportKey}/${initialView}`} language={language} documentLanguage={documentLanguage} report={report} followUp={followUp}
        initialView={initialView} evidence={evidence} onFollowQuestion={onFollowQuestion} />
      {selection}
      <div className="dw-reading-context" lang={reportLang}>
        <details className="dw-details">
          <summary>{labels.contradictions}</summary>
          {report.reported_contradictions.length > 0 && <p>{copy[documentLanguage ?? language].research.contradictionsBoundary}</p>}
          <TextEntries entries={report.reported_contradictions} empty={labels.noContradictions} />
        </details>
        <p className="dw-reading-binding">{labels.binding}</p>
      </div>
    </article>;
  }
  return (
    <article className="research-findings-reader" aria-label={t.title}>
      <h2>{t.title}</h2>
      <p className="research-binding-boundary">{t.boundary}</p>
      {selection}
      <QuestionReport key={reportKey} language={language} report={report} followUp={followUp} />
      <section aria-label={t.contradictions}>
        <h3>{t.contradictions}</h3><p>{t.contradictionsBoundary}</p>
        <TextEntries entries={report.reported_contradictions} empty={t.none} />
      </section>
      <section aria-label={t.limitations}>
        <h3>{t.limitations}</h3><TextEntries entries={report.limitations} empty={t.none} />
      </section>
    </article>
  );
}

function acceptedQuestions(report: ResearchFindingsReport, id: string) {
  return report.questions.map((question, index) => ({
    ...question,
    index,
    regionId: `${id}-question-${index}`,
    disposition: report.dispositions.find((entry) => entry.question_id === question.question_id)!,
    findings: report.findings.filter((finding) => finding.question_id === question.question_id)
  }));
}

type AcceptedQuestion = ReturnType<typeof acceptedQuestions>[number];

function useQuestionNavigation() {
  const [selectedQuestion, setSelectedQuestion] = useState<string>();
  const regions = useRef(new Map<string, HTMLElement>());
  return {
    selectedQuestion,
    registerRegion: (questionId: string, element: HTMLElement | null) => {
      if (element) regions.current.set(questionId, element);
      else regions.current.delete(questionId);
    },
    navigate: (questionId: string) => {
      setSelectedQuestion(questionId);
      const region = regions.current.get(questionId);
      region?.focus({ preventScroll: true });
      region?.scrollIntoView?.({ block: "start", behavior: "auto" });
    }
  };
}

function QuestionDirectory({ language, questions, selectedQuestion, navigate }: {
  language: Language; questions: readonly AcceptedQuestion[]; selectedQuestion?: string;
  navigate: (questionId: string) => void;
}) {
  const t = copy[language].research;
  return <nav aria-label={t.questionDirectory}>
    <ol className="research-question-list">
      {questions.map((question) => <li key={question.question_id}>
        <button type="button" aria-controls={question.regionId}
          aria-current={selectedQuestion === question.question_id ? "location" : undefined}
          onClick={() => navigate(question.question_id)}>
          <span className="research-question-number">{question.index + 1}</span>
          <span className="research-question-link-text">{question.text}</span>
          <small className={`research-question-disposition research-disposition-${question.disposition.status}`}>
            {question.disposition.status === "candidate_findings" ? t.candidateDisposition : t.unresolvedDisposition}
          </small>
        </button>
      </li>)}
    </ol>
  </nav>;
}

function QuestionReport({ language, report, followUp }: {
  language: Language; report: ResearchFindingsReport; followUp?: UnresolvedQuestionControls;
}) {
  const t = copy[language].research;
  const questions = acceptedQuestions(report, useId());
  const { selectedQuestion, registerRegion, navigate } = useQuestionNavigation();
  return <div className="research-question-report">
    <section aria-label={t.questions}>
      <h3>{t.questions}</h3>
      <QuestionDirectory language={language} questions={questions} selectedQuestion={selectedQuestion} navigate={navigate} />
    </section>
    <section aria-label={t.byQuestion}>
      <h3>{t.byQuestion}</h3>
      {questions.map((question) => <section className="research-question-findings" key={question.question_id}
        id={question.regionId} aria-labelledby={`${question.regionId}-heading`} tabIndex={-1}
        ref={(element) => registerRegion(question.question_id, element)}>
        <div className="research-question-heading">
          <p className="research-question-order">{t.questionNumber(question.index + 1)}</p>
          <small className={`research-question-disposition research-disposition-${question.disposition.status}`}>
            {question.disposition.status === "candidate_findings" ? t.candidateDisposition : t.unresolvedDisposition}
          </small>
          <h4 id={`${question.regionId}-heading`}>{question.text}</h4>
        </div>
        {question.disposition.status === "unresolved" ? <>
          <p className="research-question-reason">{question.disposition.reason}</p>
          {followUp && <UnresolvedSelection language={language} question={question} followUp={followUp} />}
        </> : question.findings.map((finding) => <article className="research-finding" key={finding.finding_id}>
          <p className="research-candidate-statement">{finding.statement}</p>
          {finding.references.map((reference, index) => <SourceInspection key={index} language={language} reference={reference} />)}
        </article>)}
      </section>)}
    </section>
  </div>;
}

function UnresolvedSelection({ language, question, followUp }: {
  language: Language; question: AcceptedQuestion; followUp: UnresolvedQuestionControls;
}) {
  const label = copy[language].research.followUp.selectQuestion(question.index + 1);
  return <label className="research-unresolved-selection">
    <input type="checkbox" aria-label={label} disabled={followUp.disabled}
      checked={followUp.selectedQuestionIds.includes(question.question_id)}
      onChange={() => followUp.onToggleQuestion(question.question_id)} />
    <span>{label}</span>
  </label>;
}

function reportTopic(question: string) {
  // A leading versioned context can stand on its own. Every title uses text from the accepted question.
  const versioned = question.match(/^(?:for\s+)?([^,，:：\n]{1,54}?\bv?\d+(?:\.\d+)+)\s*[,，:：]/i);
  if (versioned) return versioned[1];
  const points = Array.from(question.trim());
  return points.length > 60 ? `${points.slice(0, 59).join("").trimEnd()}…` : question;
}

function citationPosition(trigger: HTMLElement) {
  const positions = new Map<Element, number>();
  const scroller = trigger.ownerDocument.scrollingElement;
  for (let element = trigger.parentElement; element; element = element.parentElement) {
    if (element === scroller || /auto|scroll/.test(getComputedStyle(element).overflowY)) {
      positions.set(element, element.scrollTop);
    }
  }
  return { trigger, positions };
}

function WorkspaceQuestionReport({ language, documentLanguage, report, followUp, initialView, evidence, onFollowQuestion }: {
  language: Language;
  documentLanguage?: Language;
  report: ResearchFindingsReport;
  followUp?: UnresolvedQuestionControls;
  initialView: WorkspaceReportView;
  evidence?: readonly RunEvidenceProjection[];
  onFollowQuestion?: FollowQuestion;
}) {
  const t = copy[language].research;
  const labels = readerCopy[language];
  const documentLabels = readerCopy[documentLanguage ?? language];
  const reportLang = documentLanguage === "zh" ? "zh-CN" : documentLanguage;
  const id = useId();
  const questions = acceptedQuestions(report, id);
  const unanswered = questions.filter(({ disposition }) => disposition.status === "unresolved");
  const { selectedQuestion, registerRegion, navigate } = useQuestionNavigation();
  const [selectedCitation, setSelectedCitation] = useState<number | undefined>(initialView === "sources" ? 1 : undefined);
  const firstCitationTrigger = useRef<HTMLButtonElement>(null);
  const unresolved = useRef<HTMLElement>(null);
  const citationReturn = useRef<ReturnType<typeof citationPosition>>(undefined);
  const inspected = useRef(initialView === "sources");
  const firstCitationNumbers = new Map<string, number>();
  const references: BoundSourceReference[] = [];
  for (const finding of questions.flatMap((question) => question.findings)) {
    firstCitationNumbers.set(finding.finding_id, references.length + 1);
    references.push(...finding.references);
  }
  const sourceCount = new Set(references.map(({ source_identity }) => source_identity)).size;

  function goToUnresolved() {
    unresolved.current?.focus({ preventScroll: true });
    unresolved.current?.scrollIntoView?.({ block: "start", behavior: "auto" });
  }

  function selectCitation(number: number, trigger: HTMLElement) {
    if (selectedCitation === number) {
      setSelectedCitation(undefined);
      return;
    }
    citationReturn.current = citationPosition(trigger);
    inspected.current = true;
    setSelectedCitation(number);
  }

  useEffect(() => {
    if (initialView === "unresolved") goToUnresolved();
  }, [initialView]);

  useLayoutEffect(() => {
    if (selectedCitation !== undefined) {
      if (!citationReturn.current && firstCitationTrigger.current) {
        citationReturn.current = citationPosition(firstCitationTrigger.current);
      }
      return;
    }
    if (!inspected.current) return;
    inspected.current = false;
    const previous = citationReturn.current;
    citationReturn.current = undefined;
    (previous?.trigger ?? firstCitationTrigger.current)?.focus({ preventScroll: true });
    previous?.positions.forEach((position, element) => { element.scrollTop = position; });
  }, [selectedCitation]);

  const topic = reportTopic(questions[0].text);
  const longTopic = Array.from(topic).length > 42;
  return <div className="dw-reading-body">
    <header className="dw-reading-header">
      <h2 className={longTopic ? "dw-reading-topic-long" : undefined}>{topic}</h2>
      <div className="dw-reading-index">
        <button type="button" aria-expanded={selectedCitation === 1}
          onClick={(event) => selectCitation(1, event.currentTarget)}>{labels.citations(references.length, sourceCount)}</button>
        {unanswered.length > 0
          ? <button type="button" aria-controls={`${id}-unresolved`} onClick={goToUnresolved}>{labels.unresolvedCount(unanswered.length)}</button>
          : <span>{labels.unresolvedCount(0)}</span>}
      </div>
    </header>
    <section aria-labelledby={`${id}-findings`}>
      <h3 id={`${id}-findings`} className="dw-reading-section-title" lang={reportLang}>{documentLabels.findings}</h3>
      {questions.filter(({ findings }) => findings.length > 0).map((question) =>
        <section className="research-question-findings dw-reading-question" key={question.question_id} id={question.regionId}
          aria-label={question.text} tabIndex={-1} ref={(element) => registerRegion(question.question_id, element)}>
          {question.findings.map((finding) => <WorkspaceFinding key={finding.finding_id} language={language}
            reportLang={reportLang} finding={finding}
            firstCitation={firstCitationNumbers.get(finding.finding_id)!} selectedCitation={selectedCitation}
            firstCitationTrigger={firstCitationTrigger} evidence={evidence}
            onSelect={selectCitation} onReturn={() => setSelectedCitation(undefined)} />)}
          <details className="dw-details dw-full-question">
            <summary>{questions.length === 1 ? labels.question : `${labels.question} ${question.index + 1}`}</summary>
            <p>{question.text}</p>
          </details>
        </section>)}
    </section>
    {report.limitations.length > 0 && <section className="dw-reading-conditions" aria-labelledby={`${id}-conditions`}>
      <h3 id={`${id}-conditions`} className="dw-reading-section-title" lang={reportLang}>{documentLabels.conditions}</h3>
      <ul lang={reportLang}>{report.limitations.map((condition, index) => <li key={index}>{condition}</li>)}</ul>
    </section>}
    <section className="dw-reading-unresolved" aria-labelledby={`${id}-unresolved-title`} id={`${id}-unresolved`} tabIndex={-1} ref={unresolved}>
      <h3 id={`${id}-unresolved-title`} className="dw-reading-section-title" lang={reportLang}>{documentLabels.unresolved}</h3>
      {unanswered.length === 0 && <p lang={reportLang}>{documentLabels.noUnresolved}</p>}
      {unanswered.map((question) => <section
        className="research-question-findings dw-reading-unanswered" key={question.question_id} id={question.regionId}
        aria-label={question.text} tabIndex={-1} ref={(element) => registerRegion(question.question_id, element)}>
        <h4>{question.text}</h4>
        <p className="research-question-reason" lang={reportLang}>{question.disposition.reason}</p>
        {followUp && <UnresolvedSelection language={language} question={question} followUp={followUp} />}
        {onFollowQuestion && <button className="dw-outline" type="button"
          onClick={(event) => onFollowQuestion(question.question_id, event.currentTarget)}>{labels.continueResearch}</button>}
      </section>)}
    </section>
    <details className="dw-details dw-question-directory">
      <summary>{t.questionDirectory}</summary>
      <QuestionDirectory language={language} questions={questions} selectedQuestion={selectedQuestion} navigate={navigate} />
    </details>
  </div>;
}

function describeSource(url: string) {
  const href = safeHttpUrl(url);
  if (!href) return { title: url };
  const parsed = new URL(href);
  const blob = parsed.hostname === "github.com" && parsed.pathname.match(/^\/[^/]+\/([^/]+)\/blob\/([^/]+)\/(.+)$/);
  if (blob) {
    const [, repository, revision, path] = blob;
    const commit = /^[a-f0-9]{40}$/i.test(revision);
    return { title: `${repository} / ${path}`, revision: commit ? revision.slice(0, 7) : revision, commit };
  }
  const filename = parsed.pathname.split("/").filter(Boolean).at(-1);
  return { title: filename ? `${parsed.hostname} / ${filename}` : parsed.hostname };
}

function WorkspaceFinding({ language, reportLang, finding, firstCitation, selectedCitation, firstCitationTrigger, evidence, onSelect, onReturn }: {
  language: Language;
  reportLang?: "zh-CN" | "en";
  finding: BoundFinding;
  firstCitation: number;
  selectedCitation?: number;
  firstCitationTrigger: Ref<HTMLButtonElement>;
  evidence?: readonly RunEvidenceProjection[];
  onSelect: (number: number, trigger: HTMLButtonElement) => void;
  onReturn: () => void;
}) {
  const id = useId();
  const activeReference = selectedCitation === undefined ? undefined : finding.references[selectedCitation - firstCitation];
  const verification = activeReference && evidence?.find((entry) =>
    entry.evidence_id === activeReference.evidence_id && entry.evidence_fingerprint === activeReference.evidence_fingerprint)?.verification_status;

  return <article className="dw-reading-finding">
    <div className="dw-finding-reading">
      <p className="research-candidate-statement" lang={reportLang}>{finding.statement}</p>
      <div className="dw-citation-list">
        {finding.references.map((reference, index) => {
          const number = firstCitation + index;
          return <button key={number} className="dw-reference" type="button"
            ref={number === 1 ? firstCitationTrigger : undefined}
            aria-label={language === "zh" ? `查看来源 ${number}` : `View source ${number}`}
            aria-expanded={number === selectedCitation} aria-controls={number === selectedCitation ? `${id}-source-${number}` : undefined}
            onClick={(event) => onSelect(number, event.currentTarget)}>
            <span className="dw-citation-number">{number}</span>
            <span>{describeSource(reference.source_url).title}</span>
          </button>;
        })}
      </div>
    </div>
    {activeReference && <SourceInspection key={selectedCitation} language={language} reference={activeReference}
      workspace={{ id: `${id}-source-${selectedCitation}`, number: selectedCitation!, verification, onReturn }} />}
  </article>;
}

function TextEntries({ entries, empty }: { entries: readonly string[]; empty: string }) {
  return entries.length ? <ul>{entries.map((entry, index) => <li key={index}>{entry}</li>)}</ul> : <p>{empty}</p>;
}

function SourceInspection({ language, reference, workspace }: {
  language: Language; reference: BoundSourceReference;
  workspace?: { id: string; number: number; verification?: string; onReturn: () => void };
}) {
  const t = copy[language].research;
  const labels = readerCopy[language];
  const [open, setOpen] = useState(false);
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const snippetRegion = useRef<HTMLDivElement>(null);
  const sourceRegion = useRef<HTMLElement>(null);
  const sourceId = workspace?.id;
  const href = safeHttpUrl(reference.source_url);
  const document = workspace ? describeSource(reference.source_url) : undefined;
  const verification = workspace?.verification === "verified" ? labels.verified
    : workspace?.verification === "unverified" ? labels.unverified : labels.unknown;
  const saved = workspace ? labels.saved : t.fullSnippet;
  const returnToExcerpt = () => {
    setOpen(false);
    trigger.current?.focus({ preventScroll: true });
    trigger.current?.scrollIntoView?.({ block: "nearest", behavior: "auto" });
  };
  useEffect(() => {
    if (!sourceId) return;
    const source = sourceRegion.current;
    if (!source) return;
    source.focus({ preventScroll: true });
    if (getComputedStyle(source).position !== "fixed") {
      source.scrollIntoView?.({ block: "nearest", behavior: "auto" });
    }
  }, [sourceId]);
  useEffect(() => {
    if (open) {
      snippetRegion.current?.focus({ preventScroll: true });
      snippetRegion.current?.scrollIntoView?.({ block: "nearest", behavior: "auto" });
    }
  }, [open]);
  const Container = workspace ? "aside" : "section";
  const title = workspace ? `${t.source} ${workspace.number}` : t.source;
  return <Container className={workspace ? "research-source-inspection dw-source-panel" : "research-source-inspection"}
    aria-label={title} id={sourceId} tabIndex={workspace ? -1 : undefined} ref={sourceRegion}
    onKeyDown={workspace ? (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        if (open && snippetRegion.current?.contains(event.target as Node)) returnToExcerpt();
        else workspace.onReturn();
      }
    } : undefined}>
    {workspace && document ? <>
      <p className="dw-source-label">{labels.location(workspace.number)}</p>
      <h4 className="dw-source-heading">{document.title}</h4>
      {document.revision && <p className="dw-source-version">{document.commit ? labels.commit : labels.revision} <code>{document.revision}</code></p>}
      <p className="dw-source-status">{labels.located} · {verification}</p>
    </> : <p className="research-source-url">
      {href ? <a href={href} target="_blank" rel="noopener noreferrer">{reference.source_url}</a> : <span>{reference.source_url}</span>}
    </p>}
    {!href && <p>{t.unsafeLink}</p>}
    <strong className={workspace ? "dw-source-label" : undefined}>{workspace ? labels.excerpt : t.excerpt}</strong>
    <blockquote>{reference.excerpt}</blockquote>
    <div className={workspace ? "dw-source-actions" : undefined}>
      {workspace && href && <a href={href} target="_blank" rel="noopener noreferrer">{labels.openSource} <span aria-hidden="true">↗</span></a>}
      <button aria-expanded={open} aria-controls={open ? id : undefined} ref={trigger} type="button"
        onClick={() => setOpen((current) => !current)}>{workspace ? labels.inspect : t.inspect}</button>
    </div>
    {open && <div className="research-full-snippet" role="region" aria-label={saved} id={id} ref={snippetRegion} tabIndex={-1}>
      <h5>{saved}</h5><p>{t.snippetBoundary}</p>
      <pre>{reference.snippet}</pre>
      <button type="button" onClick={returnToExcerpt}>{t.returnToExcerpt}</button>
    </div>}
    <details className="research-binding-technical">
      <summary>{t.technical}</summary>
      <dl>
        <dt>evidence_id</dt><dd>{reference.evidence_id}</dd>
        <dt>source_identity</dt><dd>{reference.source_identity}</dd>
        <dt>evidence_fingerprint</dt><dd>{reference.evidence_fingerprint}</dd>
        <dt>excerpt_start / excerpt_end (Unicode code points)</dt><dd>{reference.excerpt_start} / {reference.excerpt_end}</dd>
      </dl>
    </details>
    {workspace && <button className="dw-return-citation" type="button" onClick={workspace.onReturn}>
      {labels.returnToCitation}
    </button>}
  </Container>;
}
