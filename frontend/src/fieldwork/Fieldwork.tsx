import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { FormEvent, MouseEvent, ReactNode } from "react";

import { FieldworkRequestError, fieldworkApi } from "./fieldworkClient";
import type { Area, Decision, Evidence, History, Item, LiveEvidence, Mode, Project, Proposal, ProposalStatus } from "./fieldworkClient";
import "./fieldwork.css";

const pages = {
  overview: "项目现场",
  stage: "阶段工作区",
  inbox: "变更收件箱",
  evidence: "证据台账",
  review: "阶段评审",
  delivery: "交付成果",
};
type Page = keyof typeof pages;
const icons: Record<Page, string> = {
  overview: "▦", stage: "◇", inbox: "✉", evidence: "▤", review: "⚑", delivery: "▱",
};
const modes: Record<Mode, string> = { replay: "离线回放", "mke-replay": "MKE 实读 · 受控分析", live: "MKE 实读 · 模型分析" };
const proposalStatuses: Record<ProposalStatus, string> = {
  pending: "待人工确认", accepted: "已采纳", returned: "已退回", superseded: "已过期",
};
const areas: Record<Area, string> = { demo: "周三演示", live_access: "实时告警读取", interview: "现场人员访谈" };
const phases = [
  { name: "需求诊断", status: "原型演示" },
  { name: "现场调查", status: "已接通" },
  { name: "方案验证", status: "待开发" },
  { name: "受控试点", status: "待验证" },
  { name: "交付复盘", status: "待开发" },
];
function affectedAreas(project: Project) {
  const retired = new Set(project.materials.filter((material) => !material.active).map((material) => material.id));
  const replacedEvidence = new Set(project.confirmed.evidence.filter((entry) => retired.has(entry.material_id)).map((entry) => entry.id));
  return new Set(project.confirmed.items.filter((item) => item.evidence_ids.some((id) => replacedEvidence.has(id))).map((item) => item.area));
}

type OpenEvidence = (evidence: Evidence, proposal: string | null, event: MouseEvent<HTMLButtonElement>) => void;

function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: string }) {
  return <span className={`fw-badge fw-badge-${tone}`}>{children}</span>;
}

function Heading({ title, description, children }: { title: string; description?: string; children?: ReactNode }) {
  return <div className="fw-intro">
    <div>
      <p className="fw-eyebrow">北辰装备 / 售后服务试点</p>
      <h1>{title}</h1>
      {description && <p className="fw-muted">{description}</p>}
    </div>
    {children && <div className="fw-buttons">{children}</div>}
  </div>;
}

function DecisionItems({ decision, proposal, openEvidence, affected }: {
  decision: Decision; proposal: string | null; openEvidence: OpenEvidence; affected?: ReadonlySet<Area>;
}) {
  const evidence = new Map(decision.evidence.map((entry) => [entry.id, entry]));
  return <ul className="fw-items">
    {decision.items.map((item) => {
      const needsReview = affected?.has(item.area);
      const canProceed = item.state === "proceed" && !needsReview;
      return <li key={item.area}>
        <span className="fw-item-icon" aria-hidden="true">{canProceed ? "✓" : "◷"}</span>
        <div className="fw-item-content">
          <strong>{item.action}</strong>
          <p>{item.reason}</p>
          <small>{areas[item.area]} · {item.owner} · {item.priority === "high" ? "高优先级" : "常规优先级"}</small>
          {item.question && <p className="fw-question">待确认：{item.question}</p>}
          <div className="fw-citations">
            {item.evidence_ids.map((id) => {
              const entry = evidence.get(id);
              return entry && <button key={id} className="fw-citation" type="button"
                aria-label={`查看依据：${entry.title}`} onClick={(event) => openEvidence(entry, proposal, event)}>
                <span aria-hidden="true">↳</span> {entry.title}
              </button>;
            })}
          </div>
        </div>
        <Badge tone={canProceed ? "green" : "amber"}>
          {needsReview ? "依据已替代，待复核" : canProceed ? "可继续" : "待确认"}
        </Badge>
      </li>;
    })}
  </ul>;
}

function ImpactMap({ items, affected }: { items: Item[]; affected?: ReadonlySet<Area> }) {
  const lead = items.find((item) => item.area === "demo");
  const branches = items.filter((item) => item !== lead);
  return <figure className="fw-impact" aria-label="当前影响范围">
    <figcaption>当前影响范围 <span aria-hidden="true">IMPACT MAP</span></figcaption>
    <div className="fw-impact-plot">
      <div className="fw-impact-origin"><span aria-hidden="true">⚑</span>
        <div><strong>{lead ? areas[lead.area] : "阶段安排"}</strong>
          <small>{lead && affected?.has(lead.area) ? "待复核" : lead?.state === "proceed" ? "可继续" : lead ? "待确认" : "当前判断"}</small></div>
      </div>
      <div className="fw-impact-branches">
        {branches.map((item) => <div key={item.area} className={`fw-impact-node fw-impact-${affected?.has(item.area) ? "waiting" : item.state}`}>
          <span className="fw-node-dot" aria-hidden="true" /><div>
            <strong>{areas[item.area]}</strong><small>{affected?.has(item.area) ? "待复核" : item.state === "proceed" ? "可独立推进" : `等待 ${item.owner}`}</small>
          </div>
        </div>)}
      </div>
    </div>
  </figure>;
}

function PhaseProgress({ stage, select }: { stage: string; select: () => void }) {
  return <section className="fw-phase-strip" aria-label="阶段进展">
    <button type="button" onClick={select}>阶段进展</button>
    <ol aria-label="阶段进展">
      {phases.map(({ name }) => <li key={name} aria-current={name === stage ? "step" : undefined}>{name}</li>)}
    </ol>
  </section>;
}

function EvidenceList({ decision, proposal, openEvidence }: {
  decision: Decision; proposal: string | null; openEvidence: OpenEvidence;
}) {
  return <ul className="fw-evidence-list">
    {decision.evidence.map((entry, index) => <li key={entry.id}>
      <button type="button" onClick={(event) => openEvidence(entry, proposal, event)}>
        <span className="fw-index">E{String(index + 1).padStart(2, "0")}</span>
        <span><strong>{entry.title}</strong><small>资料版本 {entry.material_version ?? entry.revision} · 第 {entry.page_start} 页</small></span>
        <span className="fw-row-arrow" aria-hidden="true">›</span>
      </button>
    </li>)}
  </ul>;
}

function Inbox({ project, busy, mutate, go }: {
  project: Project; busy: boolean;
  mutate: (label: string, action: () => Promise<Project>, next?: Page, applied?: () => void) => Promise<void>;
  go: (page: Page) => void;
}) {
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [predecessor, setPredecessor] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const active = project.materials.filter((material) => material.active);
  const intake = project.intake;
  const selected = active.find((material) => material.id === predecessor);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file || busy || (predecessor && !selected)) return;
    void mutate("正在上传 PDF", () => fieldworkApi.upload(file, title.trim(), predecessor), undefined, () => {
      setFile(null);
      setTitle("");
      setPredecessor("");
      if (input.current) input.current.value = "";
    });
  }

  return <>
    <Heading title="变更收件箱" description="提交客户回函，核对资料版本，再分析它对当前安排的影响。" />
    <div className="fw-grid fw-inbox-grid">
      <section className="fw-card fw-padded">
        <h2>提交业务资料</h2>
        <p className="fw-muted">支持不超过 8 MiB 的文本层 PDF。替换后旧资料与旧依据仍可查阅。</p>
        {intake && <div className="fw-recovery">
          <strong>{intake.state === "pending" ? "有一份资料尚未完成登记" : "上一次资料登记失败"}</strong>
          <p>请为「{intake.title}」重新选择同一份 PDF，并沿用原来的名称和替换对象。</p>
          <button className="fw-secondary" type="button" disabled={busy} onClick={() => {
            setTitle(intake.title);
            setPredecessor(intake.replace ?? "");
            input.current?.focus();
          }}>恢复本次提交</button>
        </div>}
        <form onSubmit={submit} className="fw-form">
          <label>录入方式
            <select value={predecessor} onChange={(event) => {
              const choice = event.target.value;
              setPredecessor(choice);
              setTitle(active.find((item) => item.id === choice)?.title ?? "");
            }} disabled={busy}>
              <option value="">新增资料</option>
              {active.map((item) => <option key={item.id} value={item.id}>替换：{item.title}（版本 {item.material_version ?? item.revision}）</option>)}
            </select>
          </label>
          <label>资料名称
            <input value={title} maxLength={120} required
              disabled={busy} onChange={(event) => setTitle(event.target.value)} />
          </label>
          <label>PDF 文件
            <input ref={input} type="file" accept="application/pdf,.pdf" aria-required="true" disabled={busy}
              onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
          </label>
          <button className="fw-primary" disabled={busy || !file || !title.trim() || (predecessor !== "" && !selected)}>
            上传 PDF
          </button>
        </form>
      </section>
      <section className="fw-card fw-padded">
        <h2>当前资料</h2>
        {project.materials.length === 0 && <p className="fw-muted">还没有提交新资料。已确认安排可在项目现场查看。</p>}
        <ul className="fw-materials">
          {project.materials.map((material) => <li key={material.id}>
            <div><strong>{material.title}</strong>
              <p className="fw-muted">资料版本 {material.material_version ?? material.revision} · {material.active ? "当前适用" : "已替代"}</p></div>
            {material.active && <button className="fw-secondary" type="button" disabled={busy || project.intake?.state === "pending"}
              onClick={() => void mutate("正在回读和分析资料", () => fieldworkApi.analyze(material.id), "review")}>分析材料</button>}
          </li>)}
        </ul>
        {project.proposal && <button className="fw-text" type="button" onClick={() => go("review")}>查看最近分析 →</button>}
      </section>
    </div>
  </>;
}

function ReviewControls({ proposal, busy, onReview }: {
  proposal: Proposal; busy: boolean; onReview: (decision: "accept" | "return", feedback: string) => void;
}) {
  const [feedback, setFeedback] = useState("");
  if (proposal.status !== "pending") {
    return proposal.feedback ? <p className="fw-feedback">评审意见：{proposal.feedback}</p> : null;
  }
  return <div className="fw-review-controls">
    <label>评审意见
      <textarea maxLength={1200} value={feedback} onChange={(event) => setFeedback(event.target.value)}
        rows={2} placeholder="退回建议时请说明原因" disabled={busy} />
    </label>
    <div className="fw-buttons">
      <button className="fw-primary" type="button" disabled={busy}
        onClick={() => onReview("accept", feedback.trim())}>采纳整份建议</button>
      <button className="fw-secondary" type="button" disabled={busy || !feedback.trim()}
        onClick={() => onReview("return", feedback.trim())}>退回建议</button>
    </div>
  </div>;
}

function EvidenceDrawer({ selected, close, mode }: {
  selected: { evidence: Evidence; proposal: string | null }; close: () => void; mode: Mode;
}) {
  const [result, setResult] = useState<LiveEvidence | "loading" | "error" | null>(null);
  const region = useRef<HTMLElement>(null);
  const { evidence, proposal } = selected;
  useLayoutEffect(() => { region.current?.focus(); }, [selected]);

  async function reread() {
    if (!proposal) return;
    setResult("loading");
    try {
      setResult(await fieldworkApi.liveEvidence(proposal, evidence.id));
    } catch {
      setResult("error");
    }
  }

  return <aside className="fw-drawer" tabIndex={-1} ref={region} role="region" aria-label="冻结原句">
    <div className="fw-drawer-head">
      <div><p className="fw-eyebrow">证据台账 / 冻结原句</p><h2>{evidence.title}</h2></div>
      <button className="fw-secondary" type="button" onClick={close}>关闭依据</button>
    </div>
    <p className="fw-muted">资料版本 {evidence.material_version ?? evidence.revision} · {evidence.page_start === evidence.page_end
      ? `第 ${evidence.page_start} 页` : `第 ${evidence.page_start}–${evidence.page_end} 页`}</p>
    <blockquote>{evidence.text}</blockquote>
    <details>
      <summary>引用与回读标识</summary>
      <dl>
        <dt>来源</dt><dd>{evidence.source_id}</dd>
        <dt>Publication</dt><dd>{evidence.publication_id} · 修订 {evidence.revision}</dd>
        <dt>Evidence</dt><dd>{evidence.id}</dd>
        <dt>生产 Run</dt><dd>{evidence.producer_run_id}</dd>
        <dt>分析 Run</dt><dd>{evidence.consumer_run_id}</dd>
        <dt>UTF-8 字节范围</dt><dd>{evidence.byte_start}–{evidence.byte_end}</dd>
        <dt>SHA-256</dt><dd>{evidence.sha256}</dd>
      </dl>
    </details>
    {proposal && evidence.producer_run_id !== "seed" && <div className="fw-live-evidence">
      <button className="fw-secondary" type="button" disabled={result === "loading"} onClick={() => void reread()}>
        核对当前回读
      </button>
      {mode === "replay" && <p>离线回放模式会核对回放资料。</p>}
      {result && <p role="status">{result === "loading" ? "正在核对…" : result === "error" || result.status === "unavailable"
        ? "当前版本无法回读这条原句，仍可核对冻结原句。"
        : "当前回读与此冻结原句一致。"}</p>}
    </div>}
  </aside>;
}

function Delivery({ project, history, refresh, busy }: {
  project: Project; history: History | null; refresh: () => void; busy: boolean;
}) {
  const versions = history?.confirmed ?? [project.confirmed];
  const html = new Map(project.deliverables.map((row) => [row.version, row.sha256]));
  return <>
    <Heading title="交付成果" description="按已确认版本下载材料，或打开已登记的离线简报。">
      <button className="fw-secondary" type="button" onClick={refresh} disabled={busy}>重新读取交付成果</button>
    </Heading>
    <div className="fw-delivery">
      {versions.map((row) => {
        const digest = html.get(row.version);
        return <article className="fw-card fw-padded" key={row.version}>
          <div className="fw-card-title"><Badge tone={row.version === project.confirmed.version ? "green" : "neutral"}>
            V{row.version} {row.version === project.confirmed.version ? "当前确认" : "历史版本"}</Badge></div>
          <h2>{row.headline}</h2>
          <div className="fw-buttons">
            {digest && <a className="fw-primary" href={fieldworkApi.export(row.version, "html")}
              target="_blank" rel="noopener noreferrer">打开 HTML</a>}
            {digest && <a className="fw-secondary" href={fieldworkApi.export(row.version, "html") + "?download=true"} download>下载 HTML</a>}
            <a className="fw-secondary" href={fieldworkApi.export(row.version, "md")} download>下载 Markdown</a>
            <a className="fw-secondary" href={fieldworkApi.export(row.version, "json")} download>下载 JSON</a>
          </div>
          {digest ? <details><summary>版本指纹</summary><p className="fw-digest">{digest}</p></details>
            : <p className="fw-muted">此版本尚未登记 HTML。</p>}
        </article>;
      })}
    </div>
  </>;
}

export default function Fieldwork() {
  const [project, setProject] = useState<Project | null>(null);
  const [page, setPage] = useState<Page>("overview");
  const [history, setHistory] = useState<History | null>(null);
  const [historical, setHistorical] = useState<Proposal | null>(null);
  const [menu, setMenu] = useState(false);
  const [selected, setSelected] = useState<{ evidence: Evidence; proposal: string | null } | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const main = useRef<HTMLElement>(null);
  const opener = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    void fieldworkApi.project(controller.signal).then((result) => {
      if (!controller.signal.aborted) setProject(result);
    }).catch(() => {
      if (!controller.signal.aborted) setError("无法读取项目，请检查本地 Fieldwork 服务后重试。");
    });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!selected) return;
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented) setSelected(null);
    };
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, [selected]);

  useLayoutEffect(() => {
    if (selected || !opener.current) return;
    if (opener.current.isConnected) opener.current.focus();
    opener.current = null;
  }, [selected]);

  async function getHistory() {
    try {
      setHistory(await fieldworkApi.history());
    } catch {
      setError("无法读取历史版本，请重新打开这一页。");
    }
  }

  function go(next: Page) {
    setPage(next);
    setMenu(false);
    opener.current = null;
    setSelected(null);
    setHistorical(null);
    setError("");
    main.current?.focus();
    if (next === "delivery" || next === "review") void getHistory();
  }

  async function refresh() {
    if (busy) return;
    setBusy("正在重新读取项目");
    setError("");
    try {
      setProject(await fieldworkApi.project());
      setHistorical(null);
      if (page === "delivery" || page === "review") await getHistory();
    } catch {
      setError("无法读取项目，请检查本地 Fieldwork 服务后重试。");
    } finally {
      setBusy("");
    }
  }

  async function mutate(label: string, action: () => Promise<Project>, next?: Page, applied?: () => void) {
    if (busy) return;
    setBusy(label);
    setError("");
    try {
      setProject(await action());
      applied?.();
      if (next) go(next);
      else if (page === "review" || page === "delivery") await getHistory();
    } catch (failure) {
      const message = failure instanceof FieldworkRequestError
        ? failure.message : "暂未收到操作回执，请先核对项目状态。";
      try {
        setProject(await fieldworkApi.project());
        if (page === "review" || page === "delivery") await getHistory();
      } catch {
        setError(`${message} 当前状态暂未读回。`);
        return;
      }
      setError(message);
    } finally {
      setBusy("");
    }
  }

  const openEvidence: OpenEvidence = (evidence, proposal, event) => {
    opener.current = event.currentTarget;
    setSelected({ evidence, proposal });
  };

  async function openHistory(id: string) {
    setError("");
    try {
      setHistorical(await fieldworkApi.proposal(id));
      main.current?.focus();
    } catch {
      setError("无法读取该建议，请稍后重试。");
    }
  }

  const confirmed = project?.confirmed;
  const pending = project?.proposal?.status === "pending" ? project.proposal : null;
  const shownDecision = pending ?? confirmed;
  const reviewed = historical ?? project?.proposal;
  const synced = busy.length === 0;
  const intakePending = project?.intake?.state === "pending";
  const affected = project ? affectedAreas(project) : undefined;
  const needsReview = (affected?.size ?? 0) !== 0;

  function navLink(key: Page) {
    return <button key={key} type="button" data-page={key} onClick={() => go(key)}
      aria-current={key === page ? "page" : undefined}><span aria-hidden="true">{icons[key]}</span>{pages[key]}</button>;
  }

  return <div className="fw-shell">
    <a className="fw-skip" href="#fw-content">跳到主要内容</a>
    <aside className={`fw-sidebar${menu ? " fw-menu-open" : ""}`}>
      <div className="fw-brand"><span className="fw-mark" aria-hidden="true" /><div>
        <strong>DRA <i>/</i> <span>Fieldwork</span></strong><small>决策研究工作台</small>
      </div></div>
      <div className="fw-side-project"><span className="fw-monogram" aria-hidden="true">北</span><div>
        <strong>北辰装备</strong><small>设备售后服务试点</small>
      </div></div>
      <nav id="fw-navigation" aria-label="工作台导航">
        <p>项目工作</p>
        {navLink("overview")}{navLink("stage")}{navLink("inbox")}
        <a href="/"><span aria-hidden="true">⌕</span>决策研究</a>
        <p>项目记录</p>
        {navLink("evidence")}{navLink("review")}{navLink("delivery")}
      </nav>
      <div className="fw-side-foot"><span aria-hidden="true">●</span> 本地工作台</div>
    </aside>
    <div className="fw-workspace">
      <header className="fw-top">
        <div className="fw-breadcrumb">
          <button className="fw-menu-toggle" type="button" aria-expanded={menu}
            aria-controls="fw-navigation" aria-label={menu ? "关闭导航" : "展开导航"}
            onClick={() => setMenu(!menu)}>☰</button>
          <span>工作区</span><span aria-hidden="true">/</span><strong>{pages[page]}</strong>
        </div>
        <div className="fw-top-end">
          {project && <Badge tone="green"><span>自编项目</span> · <span>{modes[project.mode]}</span></Badge>}
          <span className="fw-avatar" title="本机操作员" aria-label="本机操作员">我</span>
        </div>
      </header>
      <main id="fw-content" ref={main} tabIndex={-1}>
        <div className="fw-notices">
          {(busy || (!project && !error)) && <p role="status">{busy || "正在读取项目"}…</p>}
          {error && <div className="fw-alert" role="alert"><p>{error}</p>
            <button className="fw-secondary" type="button" onClick={() => void refresh()} disabled={!synced}>重新读取项目</button>
          </div>}
        </div>
        {intakePending && page !== "inbox" && <div className="fw-alert fw-recovery-link">
          <p>有一份资料尚未完成登记。确认新建议前，请回到收件箱完成上传。</p>
          <button className="fw-secondary" type="button" onClick={() => go("inbox")}>打开变更收件箱</button>
        </div>}
        {project && confirmed && shownDecision && page === "overview" && <>
          <Heading title={project.title.split(" · ").at(-1) ?? project.title}>
            <button className="fw-secondary fw-stage-shortcut" type="button" onClick={() => go("stage")}>阶段工作区</button>
            <button className="fw-primary" type="button" onClick={() => go("inbox")}>处理 IT 回函 <span aria-hidden="true">✉</span></button>
          </Heading>
          <section className="fw-judgement" aria-label="当前判断">
            <div className="fw-judgement-copy">
              <p className="fw-judgement-label"><span aria-hidden="true">✧</span> {pending ? "Agent 下一步判断 · 待确认" : needsReview ? "上次确认判断 · 部分依据待复核" : "当前已确认判断"}</p>
              <h2>{shownDecision.headline}</h2>
              <p className="fw-judgement-summary">{!pending && needsReview
                ? "部分资料已替代，请分析当前版本。行动队列仍显示可独立推进的工作。"
                : shownDecision.summary}</p>
              <div className="fw-buttons">
                <button className="fw-lime" type="button" onClick={() => go(pending ? "review" : "inbox")}>
                  {pending ? "核对待确认建议" : needsReview ? "处理替代资料" : "打开变更收件箱"} <span aria-hidden="true">→</span>
                </button>
                <button className="fw-hero-link" type="button" onClick={() => go("evidence")}>判断依据</button>
              </div>
            </div>
            <ImpactMap items={shownDecision.items} affected={pending ? undefined : affected} />
          </section>
          <PhaseProgress stage={project.stage} select={() => go("stage")} />
          <div className="fw-grid">
            <section>
              <div className="fw-section-head"><h2>行动队列</h2><small>{confirmed.items.length} 项 · V{confirmed.version} 已确认</small></div>
              <div className="fw-card"><DecisionItems decision={confirmed} proposal={confirmed.proposal_id} openEvidence={openEvidence} affected={affected} /></div>
            </section>
            <section>
              <div className="fw-section-head"><h2>项目依据</h2><button className="fw-text" type="button" onClick={() => go("evidence")}>全部材料 →</button></div>
              <div className="fw-card">
                <EvidenceList decision={shownDecision} proposal={pending?.id ?? confirmed.proposal_id} openEvidence={openEvidence} />
              </div>
              <button className="fw-review-link" type="button" onClick={() => go("review")}>
                <span aria-hidden="true">⚑</span><span><strong>阶段评审</strong><small>{pending ? "查看待确认建议" : "查看已确认安排与历史建议"}</small></span>
                <span className="fw-row-arrow" aria-hidden="true">›</span>
              </button>
            </section>
          </div>
        </>}
        {project && page === "inbox" && <Inbox project={project} busy={!synced} mutate={mutate} go={go} />}
        {project && page === "stage" && <>
          <Heading title="阶段工作区" description="目前在现场调查。确认建议后，仍可在这一阶段推进独立工作。" />
          <ul className="fw-phase-cards">
            {phases.map(({ name, status }) => <li className="fw-card fw-padded" key={name}
              aria-current={name === project.stage ? "step" : undefined}>
              <h2>{name}</h2><Badge tone={name === project.stage ? "green" : "neutral"}>{status}</Badge>
            </li>)}
          </ul>
          <div className="fw-card fw-padded fw-stage-action">
            <h2>样本准备</h2>
            <p className="fw-muted">{project.sample_prepared ? "脱敏样本已准备完成。" : "当前尚未记录样本准备完成。"}</p>
            {!project.sample_prepared && !intakePending && !affected?.has("demo") && project.confirmed.items.some((item) => item.area === "demo" && item.state === "proceed") &&
              <button className="fw-secondary" type="button" disabled={!synced}
                onClick={() => void mutate("正在记录准备状态", fieldworkApi.progress)}>记录样本已准备</button>}
          </div>
        </>}
        {project && confirmed && shownDecision && page === "evidence" && <>
          <Heading title="证据台账" description="查看当时用于判断的原句、页码与资料版本。" />
          <div className="fw-grid">
            <section className="fw-card fw-padded"><h2>{pending ? "本次建议的冻结依据" : "已确认判断的冻结依据"}</h2>
              <EvidenceList decision={shownDecision} proposal={pending?.id ?? confirmed.proposal_id} openEvidence={openEvidence} />
            </section>
            <section className="fw-card fw-padded"><h2>提交的资料与版本</h2>
              {project.materials.length === 0 && <p className="fw-muted">尚未上传 PDF。</p>}
              <ul className="fw-materials">{project.materials.map((material) => <li key={material.id}>
                <div><strong>{material.title}</strong><p className="fw-muted">资料版本 {material.material_version ?? material.revision} · {material.active ? "当前适用" : "已替代"}</p></div>
              </li>)}</ul>
            </section>
          </div>
        </>}
        {project && confirmed && page === "review" && <>
          <Heading title="阶段评审" description="对照原安排、候选变化与冻结原句，再决定是否整份采纳。" />
          <div className="fw-grid fw-review-grid">
            <section className="fw-card fw-padded">
              <div className="fw-card-title"><Badge>V{confirmed.version} 已确认</Badge></div>
              <h2>{confirmed.headline}</h2><p className="fw-muted">{confirmed.summary}</p>
              <DecisionItems decision={confirmed} proposal={confirmed.proposal_id} openEvidence={openEvidence} affected={affected} />
            </section>
            <section className="fw-card fw-padded fw-review-candidate">
              {reviewed ? <>
                <div className="fw-card-title"><Badge tone={reviewed.status === "pending" ? "amber" : "neutral"}>{proposalStatuses[reviewed.status]}</Badge>
                  <small>{modes[reviewed.mode]}</small></div>
                <h2>{reviewed.headline}</h2><p className="fw-muted">{reviewed.summary}</p>
                <DecisionItems decision={reviewed} proposal={reviewed.id} openEvidence={openEvidence} />
                {historical ? <button className="fw-secondary" type="button" onClick={() => setHistorical(null)}>返回最近建议</button>
                  : <ReviewControls key={reviewed.id} proposal={reviewed} busy={!synced || intakePending}
                    onReview={(decision, feedback) => void mutate("正在保存评审结果", () => fieldworkApi.review(reviewed.id, decision, feedback))} />}
                {reviewed.status === "accepted" && <button className="fw-text" type="button" onClick={() => go("delivery")}>查看交付成果 →</button>}
              </> : <><h2>暂无待评审建议</h2><button className="fw-secondary" type="button" onClick={() => go("inbox")}>前往变更收件箱</button></>}
            </section>
          </div>
          {history && history.proposals.some((item) => item.id !== project.proposal?.id) && <section className="fw-card fw-padded fw-history">
            <h2>以往建议</h2>
            <ul className="fw-materials">{history.proposals.filter((item) => item.id !== project.proposal?.id).map((item) => <li key={item.id}>
              <div><strong>{item.headline}</strong><p className="fw-muted">{proposalStatuses[item.status]}</p></div>
              <button className="fw-secondary" type="button" onClick={() => void openHistory(item.id)}>查看历史建议</button>
            </li>)}</ul>
          </section>}
        </>}
        {project && page === "delivery" && <Delivery project={project} history={history} refresh={() => void refresh()} busy={!synced} />}
      </main>
      {selected && project && <EvidenceDrawer key={`${selected.proposal}/${selected.evidence.id}`}
        selected={selected} mode={project.mode} close={() => setSelected(null)} />}
    </div>
  </div>;
}
