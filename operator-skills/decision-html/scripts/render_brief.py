"""Render a confirmed decision snapshot as a portable, read-only HTML brief."""

import argparse
import json
from hashlib import sha256
from html import escape
from pathlib import Path

AREA_LABELS = {"demo": "演示安排", "live_access": "实时数据访问", "interview": "现场访谈"}
STATE_LABELS = {"proceed": "可继续", "waiting": "待确认"}
PRIORITY_LABELS = {"high": "优先处理", "normal": "常规跟进"}

STYLES = """
:root {
  color-scheme: light;
  --paper: #f5f3eb;
  --sheet: #fffefa;
  --ink: #252c27;
  --muted: #505c53;
  --pine: #194c37;
  --line: #d8dcd0;
  --sage: #e5eee4;
  --bronze: #6d461a;
  --wheat: #f5ecd9;
  font: 16px/1.65 system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--paper); color: var(--ink); overflow-wrap: anywhere; }
.wrap { width: min(1080px, calc(100% - 64px)); margin-inline: auto; }
header { border-bottom: 1px solid var(--line); background: var(--sheet); }
header .wrap {
  min-height: 58px; display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 4px 16px; padding-block: 10px;
}
header strong { color: var(--pine); }
.version { color: var(--muted); font-size: .91rem; }
.hero { padding-block: 48px 32px; }
h1, h2, h3, p { margin: 0; }
h1 { max-width: 20ch; font-size: clamp(2.3rem, 5.2vw, 4.5rem); line-height: 1.12; }
.hero p { max-width: 54ch; margin-top: 16px; color: var(--muted); font-size: 1.08rem; }
h2 { font-size: 1.5rem; margin-bottom: 12px; }
.items { display: grid; gap: 12px; padding-bottom: 42px; }
article {
  min-width: 0; padding: 18px 22px; border: 1px solid var(--line);
  border-radius: 9px; background: var(--sheet);
}
.item-top { display: flex; align-items: center; flex-wrap: wrap; gap: 4px 12px; }
.area { font-size: .86rem; font-weight: 700; color: var(--pine); }
.state {
  padding: 1px 7px; border-radius: 4px; font-size: .8rem; font-weight: 650;
  background: var(--sage); color: var(--pine);
}
.state.waiting { background: var(--wheat); color: var(--bronze); }
h3 { margin: 6px 0 4px; font-size: 1.23rem; line-height: 1.35; }
dl { display: grid; grid-template-columns: 5em minmax(0, 1fr); gap: 3px 8px; margin: 9px 0; }
dt { font-weight: 650; color: var(--muted); }
dd { margin: 0; }
details { border-top: 1px solid var(--line); padding-block: 5px; }
summary { cursor: pointer; width: fit-content; color: var(--pine); font-weight: 650; }
summary:focus-visible { outline: 3px solid #94601b; outline-offset: 3px; }
blockquote { margin: 5px 0 6px; border-left: 3px solid var(--sage); padding-left: 12px; white-space: pre-wrap; }
@media (max-width: 600px) {
  .wrap { width: calc(100% - 36px); }
  .hero { padding-block: 29px 22px; }
  article { padding: 14px 15px; }
  dl { grid-template-columns: 4.25em minmax(0, 1fr); }
}
@media print {
  @page { size: A4; margin: 14mm; }
  :root { --paper: #fff; --sheet: #fff; font-size: 10pt; }
  .wrap { width: 100%; }
  .hero { padding-block: 14px; }
  h1 { max-width: none; font-size: 26pt; }
  article, details { break-inside: avoid; }
  details::details-content { content-visibility: visible; }
}
"""


def display_label(labels, key):
    return escape(labels.get(key, key))


def evidence_html(entry):
    first_page, last_page = entry["page_start"], entry["page_end"]
    if (
        type(first_page) is not int
        or type(last_page) is not int
        or not 1 <= first_page <= last_page
    ):
        raise ValueError("evidence page range")
    page_label = str(first_page) if first_page == last_page else f"{first_page}–{last_page}"
    return (
        f'<details><summary>{escape(entry["title"])} · 第 {page_label} 页</summary>'
        f'<blockquote>{escape(entry["text"])}</blockquote></details>'
    )


def item_html(item, evidence):
    owner, reason = escape(item["owner"]), escape(item["reason"])
    action, question = escape(item["action"]), escape(item["question"])
    area = display_label(AREA_LABELS, item["area"])
    state = display_label(STATE_LABELS, item["state"])
    priority = display_label(PRIORITY_LABELS, item["priority"])
    style = " waiting" if item["state"] == "waiting" else ""
    question_row = f"<dt>待确认</dt><dd>{question}</dd>" if question else ""
    references = item["evidence_ids"]
    if not isinstance(references, list) or any(reference not in evidence for reference in references):
        raise ValueError("item evidence references")
    sources = "\n".join(evidence_html(evidence[reference]) for reference in dict.fromkeys(references))
    return f"""<article>
  <div class="item-top"><span class="area">{area}</span><span class="state{style}">{state}</span></div>
  <h3>{action}</h3>
  <p>{reason}</p>
  <dl><dt>负责人</dt><dd>{owner}</dd><dt>优先级</dt><dd>{priority}</dd>{question_row}</dl>
  {sources}
</article>"""


def render(snapshot, *, fictional=False):
    version = snapshot["version"]
    if type(version) is not int or version < 1:
        raise ValueError("snapshot version")
    if not isinstance(snapshot["evidence"], list) or not isinstance(snapshot["items"], list):
        raise ValueError("snapshot items and evidence")
    evidence = {entry["id"]: entry for entry in snapshot["evidence"]}
    if len(evidence) != len(snapshot["evidence"]):
        raise ValueError("duplicate evidence id")
    title = escape(snapshot["headline"])
    summary = escape(snapshot["summary"])
    # Match the canonical JSON fingerprint checked by the Fieldwork registrar.
    canonical = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    fingerprint = sha256(canonical.encode("utf-8")).hexdigest()
    cards = "\n".join(item_html(item, evidence) for item in snapshot["items"])
    identity = "决策简报 · 虚构案例" if fictional else "决策简报"

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="fieldwork-snapshot-sha256" content="{fingerprint}">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>{title} · 决策简报</title>
<style>{STYLES}</style>
</head>
<body>
<header><div class="wrap"><strong>{identity}</strong><span class="version">版本 {version}</span></div></header>
<main class="wrap">
  <div class="hero"><h1>{title}</h1><p>{summary}</p></div>
  <section aria-labelledby="actions">
    <h2 id="actions">已确认的安排</h2>
    <div class="items">{cards}</div>
  </section>
</main>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="confirmed version JSON")
    parser.add_argument("output", type=Path, help="destination HTML file")
    parser.add_argument("--fictional", action="store_true", help="label an illustrative case")
    args = parser.parse_args()
    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        content = render(snapshot, fictional=args.fictional)
    except (UnicodeError, TypeError, ValueError, KeyError, AttributeError):
        parser.error("invalid confirmed snapshot or evidence reference")
    args.output.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
