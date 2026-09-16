import { createElement, useState, type ReactNode } from "react";

import { type Observation, type ResultView } from "../consoleProjection";
import { copy, type Language } from "../i18n";
import { KeyValueList, ObservationValue } from "./observation";

export type ResultReaderMode = "static" | "live";
type ReaderView = "formatted" | "raw";

export function ResultReader({
  language,
  mode,
  result
}: {
  language: Language;
  mode: ResultReaderMode;
  result: Observation<ResultView>;
}) {
  const t = copy[language].reader;
  const [view, setView] = useState<ReaderView>("formatted");

  if (result.kind !== "observed") {
    return (
      <article className={`result-reader result-reader-${result.kind}`} aria-label={t.title}>
        <div className="reader-empty-heading">
          <div>
            <p className="kicker">{t.title}</p>
            <h3>{t.unavailableTitle}</h3>
          </div>
          <span className={`showcase-badge ${result.kind === "not_applicable" ? "blocked" : "neutral"}`}>
            {mode === "static" ? t.staticMode : t.liveMode}
          </span>
        </div>
        <ObservationValue language={language} observation={result} />
        {result.kind === "not_applicable" && <p className="reader-empty-note">{t.unavailableDetail}</p>}
      </article>
    );
  }

  const artifact = result.value.artifact;
  return (
    <article className="result-reader" aria-label={t.title}>
      <div className="reader-heading">
        <div>
          <p className="kicker">{t.title}</p>
          <h3>{t.documentLabel}</h3>
          <p className="reader-artifact-name">{artifact.artifactId}</p>
        </div>
        <div className="reader-actions">
          <span className={`showcase-badge ${mode === "static" ? "ready" : "neutral"}`}>
            {mode === "static" ? t.staticMode : t.liveMode}
          </span>
          <button type="button" onClick={() => downloadArtifact(artifact.content, artifact.artifactId)}>
            {t.download}
          </button>
        </div>
      </div>
      <div className="reader-meta" aria-label={t.metadataLabel}>
        <span>{t.serviceReportedHash}</span>
        <code>{artifact.contentHash}</code>
        <span>{t.exactBytes}</span>
      </div>
      <div className="reader-tabs" role="tablist" aria-label={t.viewLabel}>
        <button
          aria-selected={view === "formatted"}
          className={view === "formatted" ? "active" : ""}
          role="tab"
          type="button"
          onClick={() => setView("formatted")}
        >
          {t.readView}
        </button>
        <button
          aria-selected={view === "raw"}
          className={view === "raw" ? "active" : ""}
          role="tab"
          type="button"
          onClick={() => setView("raw")}
        >
          {t.rawView}
        </button>
      </div>
      {view === "formatted" ? (
        <SafeMarkdownDocument content={artifact.content} />
      ) : (
        <pre className="raw-artifact" role="tabpanel">
          {artifact.content}
        </pre>
      )}
      <details className="reader-technical">
        <summary>{t.technicalDetails}</summary>
        <KeyValueList
          entries={[
            ["run_id", result.value.runId],
            ["artifact_id", artifact.artifactId],
            ["media_type", artifact.mediaType],
            ["content_hash", artifact.contentHash],
            ["execution_status", <ObservationValue language={language} observation={result.value.executionStatus} />],
            ["delivery_status", <ObservationValue language={language} observation={result.value.deliveryStatus} />],
            ["revision", <ObservationValue language={language} observation={artifact.revision} />],
            ["safety", <ObservationValue language={language} observation={artifact.safety} />]
          ]}
        />
      </details>
    </article>
  );
}

export function SafeMarkdownDocument({ content }: { content: string }) {
  return <div className="safe-markdown">{parseSafeMarkdown(content)}</div>;
}

export function sanitizeArtifactFilename(artifactId: string): string {
  const cleaned = artifactId
    .replace(/\.md$/i, "")
    .replace(/[^A-Za-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 96);
  const base = cleaned || "research-report";
  return `${base.toLowerCase()}.md`;
}

export function downloadArtifact(content: string, artifactId: string): boolean {
  if (
    typeof document === "undefined" ||
    typeof URL === "undefined" ||
    typeof URL.createObjectURL !== "function"
  ) {
    return false;
  }
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = sanitizeArtifactFilename(artifactId);
  link.hidden = true;
  document.body.appendChild(link);
  link.click();
  link.remove();
  if (typeof URL.revokeObjectURL === "function") {
    URL.revokeObjectURL(objectUrl);
  }
  return true;
}

export function safeHttpUrl(value: string): string | undefined {
  try {
    const parsed = new URL(value);
    if (
      (parsed.protocol !== "http:" && parsed.protocol !== "https:") ||
      parsed.username !== "" ||
      parsed.password !== ""
    ) {
      return undefined;
    }
    return parsed.href;
  } catch {
    return undefined;
  }
}

type MarkdownBlock =
  | { kind: "heading"; level: number; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "unordered"; items: readonly string[] }
  | { kind: "ordered"; items: readonly string[] }
  | { kind: "code"; text: string; language?: string };

function parseSafeMarkdown(content: string): ReactNode[] {
  const blocks = parseBlocks(content);
  return blocks.map((block, index) => {
    switch (block.kind) {
      case "heading": {
        return createElement(`h${Math.min(block.level, 6)}`, { key: `heading-${index}` }, block.text);
      }
      case "paragraph":
        return <p key={`paragraph-${index}`}>{block.text}</p>;
      case "unordered":
        return (
          <ul key={`unordered-${index}`}>
            {block.items.map((item, itemIndex) => <li key={`item-${itemIndex}`}>{item}</li>)}
          </ul>
        );
      case "ordered":
        return (
          <ol key={`ordered-${index}`}>
            {block.items.map((item, itemIndex) => <li key={`item-${itemIndex}`}>{item}</li>)}
          </ol>
        );
      case "code":
        return (
          <pre key={`code-${index}`}>
            {block.text}
          </pre>
        );
    }
  });
}

function parseBlocks(content: string): MarkdownBlock[] {
  const blocks: MarkdownBlock[] = [];
  const lines = content.replace(/\r\n?/g, "\n").split("\n");
  let paragraph: string[] = [];
  let listKind: "unordered" | "ordered" | null = null;
  let listItems: string[] = [];
  let codeLines: string[] = [];
  let codeLanguage: string | undefined;

  const flushParagraph = () => {
    if (paragraph.length > 0) {
      blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
      paragraph = [];
    }
  };
  const flushList = () => {
    if (listKind !== null && listItems.length > 0) {
      blocks.push({ kind: listKind, items: [...listItems] });
    }
    listKind = null;
    listItems = [];
  };

  let inCode = false;
  for (const line of lines) {
    if (line.trimStart().startsWith("```")) {
      flushParagraph();
      flushList();
      if (inCode) {
        blocks.push({ kind: "code", text: codeLines.join("\n"), language: codeLanguage });
        codeLines = [];
        codeLanguage = undefined;
        inCode = false;
      } else {
        inCode = true;
        codeLanguage = line.trim().slice(3).trim() || undefined;
      }
      continue;
    }
    if (inCode) {
      codeLines.push(line);
      continue;
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      flushList();
      blocks.push({ kind: "heading", level: heading[1].length, text: heading[2] });
      continue;
    }
    if (line.trim() === "") {
      flushParagraph();
      flushList();
      continue;
    }

    const unordered = line.match(/^\s*[-*]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (unordered || ordered) {
      flushParagraph();
      const nextKind = unordered ? "unordered" : "ordered";
      if (listKind !== null && listKind !== nextKind) {
        flushList();
      }
      listKind = nextKind;
      listItems.push((unordered ?? ordered)?.[1] ?? "");
      continue;
    }

    if (listKind !== null) {
      flushList();
    }
    paragraph.push(line.trim());
  }

  if (inCode) {
    blocks.push({ kind: "code", text: codeLines.join("\n"), language: codeLanguage });
  }
  flushParagraph();
  flushList();
  return blocks;
}
