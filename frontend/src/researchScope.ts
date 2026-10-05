import type { ResearchQuestion } from "./researchFindings";

export const RESEARCH_QUESTIONS_MAX = 5;
export const RESEARCH_QUESTION_CODE_POINTS_MAX = 4096;

export type ResearchScopeValidation = Readonly<
  | { ok: true }
  | { ok: false; reason: "count" | "question_id" | "duplicate_id" | "blank" | "too_large"; index?: number }
>;

/** Consumer input checks only; accepted scope and delivery remain server-owned. */
export function validateResearchQuestions(questions: readonly ResearchQuestion[]): ResearchScopeValidation {
  if (questions.length < 1 || questions.length > RESEARCH_QUESTIONS_MAX) {
    return Object.freeze({ ok: false, reason: "count" });
  }
  const ids = new Set<string>();
  for (const [index, question] of questions.entries()) {
    if (typeof question.question_id !== "string" ||
        /^[A-Za-z][A-Za-z0-9_-]{0,63}$/.exec(question.question_id)?.[0] !== question.question_id) {
      return Object.freeze({ ok: false, reason: "question_id", index });
    }
    if (ids.has(question.question_id)) {
      return Object.freeze({ ok: false, reason: "duplicate_id", index });
    }
    ids.add(question.question_id);
    if (typeof question.text !== "string" || !question.text.trim()) {
      return Object.freeze({ ok: false, reason: "blank", index });
    }
    if (Array.from(question.text).length > RESEARCH_QUESTION_CODE_POINTS_MAX) {
      return Object.freeze({ ok: false, reason: "too_large", index });
    }
  }
  return Object.freeze({ ok: true });
}
