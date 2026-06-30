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
- [x] Controlled single-node review API and CLI workflow.
- [x] Agent Research Operations Console with deterministic Static Demo and
  bounded local Live Backend run/result flow.
- [ ] Add live controlled-review and evidence-verification controls only after
  demo usage shows that the existing CLI workflows are insufficient.
- [ ] Multi-user identity/RBAC.
- [ ] Shared database and multi-instance worker coordination.
- Keep durable HITL disabled by default. Enable controlled review only inside the documented
  controlled single-node boundary after `doctor` and all thirteen gates pass.

## Delivery Channels

- Evaluate ATS, dashboard, email, spreadsheet, and other delivery adapters after
  the canonical Markdown artifact and its readability gate are stable.
- Evaluate persona-specific prioritization only when the contract can represent
  role relevance or business priority without treating model confidence as
  importance.

## Agent Capabilities

- Keep additional runtime Skills, Async Subagents, and LLM review deferred until
  benchmark evidence demonstrates a specific limitation they solve.

# Post-v0.1.0 CLI DX

- [x] Add a bounded `run --wait --result` convenience flow
  after the canonical run/result contract has shipped and real usage shows the
  extra command is material friction.
- [x] Render Tool Client HTTP failures consistently as structured
  `problem` / `cause` / `fix` output without exposing raw response bodies or
  tracebacks.
