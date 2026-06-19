# Deferred Work

These items are intentionally outside the Talent DecisionBrief renderer-v2
readability milestone. They require separate evidence, design, and approval.

## Presentation Contract

- Evaluate a dedicated structured presentation schema only after a second
  consumer (for example, UI or export adapter) demonstrates that renderer-only
  derivation is insufficient.
- Evaluate explicit input/list size limits for findings, claims, and evidence.
  Do not add silent renderer truncation.

## Decision Workflow

- Evaluate JD recommendations, interview verification questions, and candidate
  evaluation only with a separately approved evidence and review policy.
- Implement P1B durable HITL only after its persistence, restart recovery,
  idempotency, lease/reclaim, and kill-9 safety gates pass.

## Delivery Channels

- Evaluate ATS, dashboard, email, spreadsheet, and other delivery adapters after
  the canonical Markdown artifact and its readability gate are stable.
- Evaluate persona-specific prioritization only when the contract can represent
  role relevance or business priority without treating model confidence as
  importance.

## Agent Capabilities

- Keep runtime Skills, Async Subagents, and LLM review deferred until benchmark
  evidence demonstrates a specific limitation they solve.
