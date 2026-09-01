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
- preparation/terminal publication state contract checks, including immutable
  release-note and changelog-section byte identities;
- documentation coverage for reference, how-to, tutorial, and explanation
  surfaces, discoverability, command/link validity, changelog preservation,
  public/private markers, secrets, and diagram drift.

No real-provider request, hosted Console claim, deployment, business-impact
metric, API/schema/domain change, dependency choice, or historical release
mutation is part of this plan.

## Terminal Publication Package

The approved terminal path has exactly two sequential stages:

1. **Release-prep PR and publication gate.** After authority review, create the
   release-prep PR from the exact reviewed commit. Merge only after the exact
   reviewed head/tree and exact-main hosted checks are read back. Then, under
   separate authorization, create the annotated `v0.1.9` tag, publish the
   GitHub Release, and complete the official source-archive proof. The tag and
   Release body must be sourced from the exact merge commit, not a mutable
   checkout.
2. **Same-scope post-publication docs closeout PR.** After publication and all
   readbacks succeed, create one closeout PR in the same release-metadata/docs
   scope. It must keep the tag's `docs/releases/v0.1.9.md` and `[0.1.9]`
   `CHANGELOG.md` section byte-identical, while updating the mutable README,
   bilingual README, docs index, `SECURITY.md`, Superpowers index, and this
   plan so `v0.1.9` is the current published stable release.

This implementation phase is still before both terminal stages. No PR, merge,
tag, GitHub Release, official source-archive receipt, or publication fact may
be inferred from this local commit.

## Terminal Publication Record

Publication status: preparation.

No terminal publication facts exist in this preparation state. The following
JSON is a state marker, not a publication receipt. The same-scope
post-publication docs closeout PR must replace this entire state marker with a
complete JSON record containing actual readback values; do not prefill fields
with placeholders, `null`, `TBD`, or expected values.

```json
{
  "state": "preparation"
}
```

When the record becomes `published`, the exact required fields are:

- state envelope: `schema_version` and `state`;
- release-prep PR: `release_prep_pr_number`, `release_prep_pr_url`,
  `release_prep_reviewed_head`, `release_prep_merge_commit`,
  `release_prep_merge_tree`;
- post-publication docs closeout PR: `post_publication_pr_number`,
  `post_publication_pr_url`, `post_publication_reviewed_head`,
  `post_publication_merge_commit`, `post_publication_merge_tree`;
- tag and Release: `tag_name`, `tag_object`, `peeled_commit`, `tag_tree`,
  `release_id`, `release_url`, `release_published_at`, `release_state`,
  `release_is_draft`, `release_is_prerelease`, `release_body_sha256`;
- immutable body identities: `tag_release_note_sha256`,
  `tag_changelog_section_sha256`;
- official source archive: `archive_filename`, `archive_bytes`,
  `archive_sha256`, `archive_safe_extraction`, `archive_git_free_smoke`;
- exact-main hosted evidence and closeout: `exact_main_hosted_checks`,
  `non_claims`, and `cleanup`.

The owning `release_publication_contract.py` rejects premature publication
claims in the preparation state. In the published state it requires every
field above, checks the annotated-tag/merge identities and Release body hash,
requires successful checks on the exact release merge commit, verifies the
frozen release note and changelog-section bytes, and rejects mutable entrypoints
that still call `v0.1.8` the last published stable release or `v0.1.9` a
preparation.
