# Agent Research Operations Console Showcase Refinement Plan

Status: Complete

## Goal

Refine the existing Static Demo presentation so a non-technical reader can
follow one deterministic research path from question to Evidence review and
canonical delivery, while keeping the current Live Backend consumer and all
service-owned authority boundaries unchanged.

## Scope

1. Add RED/GREEN contracts for the three-layer presentation hierarchy, the
   normal and blocked static showcase states, the exact three-image manifest,
   and the reordered public README entry sections.
2. Implement presentation-only `stage rail -> research work surface ->
   judgment sidebar` labels and deterministic static showcase query states.
   Keep runtime IDs, mode details, framework names, and traces in a secondary
   technical disclosure. A blocked state must remain review-required and
   not-delivered.
3. Capture `research-workspace-overview.png`, `research-evidence-review.png`,
   and `research-blocked-recovery.png` at 1600x1000 from one stable
   implementation commit/tree. Record route/state, locale, viewport,
   SHA-256, source commit/tree, and the synthetic/demo disclosure in the
   manifest without self-referencing the asset commit.
4. Reorder the first README layers to value, overview, five-step flow, normal
   and blocked frames, engineering judgments, quickstart, authority details,
   and deeper architecture/evaluation/release material. Preserve historical
   release and evidence records.
5. Run focused frontend/Python contracts, frontend CI-parity checks, browser
   QA at showcase and narrow viewports, public/private marker scans, and
   `git diff --check` before clean local commits. Do not modify backend, API,
   database, runtime, framework, release, or remote state.

## Closeout

Mark this plan complete only after the implementation source commit is frozen,
the three assets and manifest verify deterministically, all proportional checks
pass, the final diff is public-neutral, and the worktree is clean.

## Mini-retro

- A green PR-head run does not prove that a squash-merged main checkout can
  resolve the PR's historic source commit.
- Presentation provenance guards must remain portable on a fresh main clone:
  hard-verify the current rendering-input fingerprint, and report when
  historic identity is unavailable instead of claiming historic verification.
