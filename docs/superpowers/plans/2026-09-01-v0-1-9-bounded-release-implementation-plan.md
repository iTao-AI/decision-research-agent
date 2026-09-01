# Decision Research Agent v0.1.9 Bounded Release Implementation Plan

Date: 2026-09-01

Status: approved for implementation

## Scope

Prepare the next bounded Decision Research Agent source release from the
approved default-branch base `875171fc5fc7b33d304bf7bc30907035f8d6c537`
(`ab12e70a88882b05da36a9fbc3fb339d0c390606`). The release preparation records
the capabilities already merged after stable `v0.1.8` and does not change
backend behavior, API or schema contracts, domain authority, dependencies,
providers, deployment, or package-registry state.

The stable `v0.1.8` release record remains historical and immutable. The
release record and changelog for `v0.1.9` must remain explicit about provider-
free, local-only, non-production verification and the absence of business
impact or adoption claims.

## Included current-main facts

- Frontend transitive security-lock maintenance.
- Native deterministic Console showcase frames and squash-portable provenance.
- Maintained Node.js 22/24 support metadata and CI lanes.
- Frontend test-patch and showcase-provenance refresh.
- Bounded blocked-failure diagnosis that preserves `review_required` and
  `not_delivered` for the failed source.
- One bounded user-authored Live Backend research question with exact-query
  replay rules.
- GET-only reattachment of a retained known `run_id`, without run history,
  listing, browser persistence, or ambiguous POST replay.

## Implementation sequence

1. Freeze current release truth in focused tests before changing implementation
   files. The first run must fail on the stale `0.1.8` identity or missing
   `v0.1.9` release record.
2. Change only project-owned release identity to `0.1.9` in `VERSION`, the
   frontend package metadata and lock root, and their owning tests/contracts.
3. Move the complete current `[Unreleased]` inventory into the dated
   `[0.1.9]` changelog section without changing any older release entry.
4. Add `docs/releases/v0.1.9.md` with the supported surface, changes,
   compatibility, rollback, required verification, and known limits. Update
   current README, bilingual README, documentation indexes, release
   navigation, security wording, and the public-neutral implementation index
   only where the current release truth requires it.
5. Verify the release candidate with the repository's locked provider-free
   backend and frontend lanes, secure local runtime/Compose gates, canonical
   identity and presentation checks, clean-tree source/archive checks, and a
   targeted Diataxis documentation audit.

## Verification boundaries

Required evidence is limited to commands that can run without a real provider:

- focused current-release contract RED then GREEN;
- locked provider-free backend proofs and `python -m pytest -q -m "not docker"`;
- frontend `npm ci`, tests, lint, build, and moderate-level audit on Node.js
  22 and 24 where the local environment supports both maintained lanes;
- secure local runtime and task-owned Compose resources, with host, VM,
  container, image, volume, and port inventory before and after use;
- release verifier, canonical identity, presentation, clean-tree build, and
  Git-free source-candidate/archive checks;
- documentation coverage for reference, how-to, tutorial, and explanation
  surfaces, discoverability, command/link validity, changelog preservation,
  public/private markers, secrets, and diagram drift.

No real-provider request, hosted Console claim, deployment, business-impact
metric, API/schema/domain change, dependency choice, or historical release
mutation is part of this plan.

## Publication boundary

This implementation phase ends after the reviewed local commit and clean
verification receipt. Push, pull request, merge, tag, GitHub Release, official
source-archive receipt, and task-owned cleanup are separate gated actions and
must use the exact reviewed state when explicitly authorized.
