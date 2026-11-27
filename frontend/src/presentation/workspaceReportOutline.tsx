import { useId, useLayoutEffect, useRef, useState } from "react";
import type { Language } from "../i18n";

const outlineCopy = {
  zh: {
    label: "结构示意",
    instructions: "报告按研究问题组织。点结论旁的引文，可以查到这条结论依据的原文。",
    reference: "查看引文 1 的原文位置",
    sourceHeading: "引用原文的位置",
    sourceDescription: "实际报告会在这里显示与该结论绑定的摘录和来源链接。",
    back: "返回引文"
  },
  en: {
    label: "Illustrative structure",
    instructions: "Reports are organized by question. Open a citation next to a finding to see its supporting passage.",
    reference: "See where citation 1 opens",
    sourceHeading: "Where the cited passage appears",
    sourceDescription: "A delivered report shows the passage and source link associated with the finding here.",
    back: "Back to citation"
  }
};

export function WorkspaceReportOutline({ language }: { language: Language }) {
  const t = outlineCopy[language];
  const id = useId();
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);

  useLayoutEffect(() => {
    if (open) heading.current?.focus({ preventScroll: true });
  }, [open]);

  function closeSource() {
    setOpen(false);
    trigger.current?.focus({ preventScroll: true });
  }

  return <section className="dw-outline-lesson" aria-label={t.label}>
    <strong>{t.label}</strong>
    <p>{t.instructions}{" "}
      <button className="dw-reference" type="button" ref={trigger} aria-label={t.reference}
        aria-expanded={open} aria-controls={id} onClick={() => open ? closeSource() : setOpen(true)}>[1]</button>
    </p>
    <section id={id} className="dw-notice" hidden={!open} onKeyDown={(event) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      closeSource();
    }}>
      <h3 ref={heading} tabIndex={-1}>{t.sourceHeading}</h3>
      <p>{t.sourceDescription}</p>
      <button className="dw-outline" type="button" onClick={closeSource}>{t.back}</button>
    </section>
  </section>;
}
