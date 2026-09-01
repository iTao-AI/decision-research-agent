# Decision Research Agent v0.1.9 Bounded Release Implementation Plan

Date: 2026-09-01

Status: Stage 2 post-publication docs closeout pending authority review

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

Stage 1 release-prep PR #149 and publication completed from the exact approved
merge commit. Stage 2 is now prepared on that exact release merge and remains
local-only pending authority review; no closeout PR has been created or pushed.
The tagged release note and `[0.1.9]` changelog section remain immutable. The
terminal record below contains only causal Stage 1 facts and deliberately omits
closeout PR self-identity and post-merge cleanup.

## Terminal Publication Record

Publication status: published.

The following causal JSON is the complete Stage 1 publication readback. Every
value was read from the exact release-prep PR, exact merge commit, hosted
checks, annotated tag, GitHub Release, or official source archive before this
Stage 2 closeout branch was created. It contains no placeholders, `null`,
`TBD`, expected values, closeout PR self-identity, or post-merge cleanup. The
closeout PR identity and cleanup callback belong only in the final persisted
closeout PR body and authority terminal callback/readback.

```json
{
  "archive_bytes": 2307343,
  "archive_filename": "decision-research-agent-0.1.9.tar.gz",
  "archive_git_free_smoke": true,
  "archive_safe_extraction": true,
  "archive_sha256": "086432ed7a4bcf5addad316f98d9404d6c16a67b5eeaa797a43977593229d588",
  "exact_main_hosted_checks": [
    {
      "head_sha": "e748870fd77257bb716b17bdc007099a4ff58a0b",
      "name": "Backend Tests",
      "run_id": 99899183518,
      "status": "success",
      "url": "https://github.com/iTao-AI/decision-research-agent/actions/runs/33520781422/job/99899183518"
    },
    {
      "head_sha": "e748870fd77257bb716b17bdc007099a4ff58a0b",
      "name": "Secure Local Runtime Containers",
      "run_id": 99899183220,
      "status": "success",
      "url": "https://github.com/iTao-AI/decision-research-agent/actions/runs/33520781422/job/99899183220"
    },
    {
      "head_sha": "e748870fd77257bb716b17bdc007099a4ff58a0b",
      "name": "Frontend Demo Console (Node 22.22.2)",
      "run_id": 99899183532,
      "status": "success",
      "url": "https://github.com/iTao-AI/decision-research-agent/actions/runs/33520781422/job/99899183532"
    },
    {
      "head_sha": "e748870fd77257bb716b17bdc007099a4ff58a0b",
      "name": "Frontend Demo Console (Node 24.15.0)",
      "run_id": 99899183592,
      "status": "success",
      "url": "https://github.com/iTao-AI/decision-research-agent/actions/runs/33520781422/job/99899183592"
    },
    {
      "head_sha": "e748870fd77257bb716b17bdc007099a4ff58a0b",
      "name": "Analyze (actions)",
      "run_id": 99899190419,
      "status": "success",
      "url": "https://github.com/iTao-AI/decision-research-agent/actions/runs/33520781343/job/99899190419"
    },
    {
      "head_sha": "e748870fd77257bb716b17bdc007099a4ff58a0b",
      "name": "Analyze (javascript-typescript)",
      "run_id": 99899190397,
      "status": "success",
      "url": "https://github.com/iTao-AI/decision-research-agent/actions/runs/33520781343/job/99899190397"
    },
    {
      "head_sha": "e748870fd77257bb716b17bdc007099a4ff58a0b",
      "name": "Analyze (python)",
      "run_id": 99899190136,
      "status": "success",
      "url": "https://github.com/iTao-AI/decision-research-agent/actions/runs/33520781343/job/99899190136"
    }
  ],
  "non_claims": [
    "No real-provider research or business-impact claim is made.",
    "No hosted Console operation, deployment, production-readiness, or adoption claim is made.",
    "Human review and release authority remain outside the Console."
  ],
  "peeled_commit": "e748870fd77257bb716b17bdc007099a4ff58a0b",
  "release_body_sha256": "c704c3aced1c46d6ae75fc4ac9c036e53821f297d0535c3f29ec3a6b6f2c2a37",
  "release_id": 380597208,
  "release_is_draft": false,
  "release_is_prerelease": false,
  "release_prep_merge_commit": "e748870fd77257bb716b17bdc007099a4ff58a0b",
  "release_prep_merge_tree": "29736bcf7c106bfa66be7cbb306a42430460b1fe",
  "release_prep_pr_number": 149,
  "release_prep_pr_url": "https://github.com/iTao-AI/decision-research-agent/pull/149",
  "release_prep_reviewed_head": "3af482f93a43f4950d355520cf678b18e8f9cf5f",
  "release_prep_reviewed_tree": "29736bcf7c106bfa66be7cbb306a42430460b1fe",
  "release_published_at": "2026-09-01T14:54:14Z",
  "release_state": "published",
  "release_url": "https://github.com/iTao-AI/decision-research-agent/releases/tag/v0.1.9",
  "reviewed_head_hosted_checks": [
    {
      "head_sha": "3af482f93a43f4950d355520cf678b18e8f9cf5f",
      "name": "Backend Tests",
      "run_id": 99895610898,
      "status": "success",
      "url": "https://github.com/iTao-AI/decision-research-agent/actions/runs/33519722406/job/99895610898"
    },
    {
      "head_sha": "3af482f93a43f4950d355520cf678b18e8f9cf5f",
      "name": "Secure Local Runtime Containers",
      "run_id": 99895611349,
      "status": "success",
      "url": "https://github.com/iTao-AI/decision-research-agent/actions/runs/33519722406/job/99895611349"
    },
    {
      "head_sha": "3af482f93a43f4950d355520cf678b18e8f9cf5f",
      "name": "Frontend Demo Console (Node 22.22.2)",
      "run_id": 99895611174,
      "status": "success",
      "url": "https://github.com/iTao-AI/decision-research-agent/actions/runs/33519722406/job/99895611174"
    },
    {
      "head_sha": "3af482f93a43f4950d355520cf678b18e8f9cf5f",
      "name": "Frontend Demo Console (Node 24.15.0)",
      "run_id": 99895611335,
      "status": "success",
      "url": "https://github.com/iTao-AI/decision-research-agent/actions/runs/33519722406/job/99895611335"
    },
    {
      "head_sha": "3af482f93a43f4950d355520cf678b18e8f9cf5f",
      "name": "Analyze (actions)",
      "run_id": 99895608823,
      "status": "success",
      "url": "https://github.com/iTao-AI/decision-research-agent/actions/runs/33519720453/job/99895608823"
    },
    {
      "head_sha": "3af482f93a43f4950d355520cf678b18e8f9cf5f",
      "name": "Analyze (javascript-typescript)",
      "run_id": 99895609209,
      "status": "success",
      "url": "https://github.com/iTao-AI/decision-research-agent/actions/runs/33519720453/job/99895609209"
    },
    {
      "head_sha": "3af482f93a43f4950d355520cf678b18e8f9cf5f",
      "name": "Analyze (python)",
      "run_id": 99895609212,
      "status": "success",
      "url": "https://github.com/iTao-AI/decision-research-agent/actions/runs/33519720453/job/99895609212"
    },
    {
      "head_sha": "3af482f93a43f4950d355520cf678b18e8f9cf5f",
      "name": "CodeQL",
      "run_id": 99895824437,
      "status": "success",
      "url": "https://github.com/iTao-AI/decision-research-agent/runs/99895824437"
    }
  ],
  "schema_version": "dra.v0.1.9-publication-record.v1",
  "state": "published",
  "tag_changelog_section_sha256": "2325ba03f2f66aec3c4371c9fafd34b1b5b56b71e377bcdb59c18419feff7f14",
  "tag_name": "v0.1.9",
  "tag_object": "4e6e190bc974e6896009244f7c33fa8f3f497509",
  "tag_release_note_sha256": "c704c3aced1c46d6ae75fc4ac9c036e53821f297d0535c3f29ec3a6b6f2c2a37",
  "tag_tree": "29736bcf7c106bfa66be7cbb306a42430460b1fe"
}
```

The published record has the following exact required fields:

- state envelope: `schema_version` and `state`;
- release-prep PR: `release_prep_pr_number`, `release_prep_pr_url`,
  `release_prep_reviewed_head`, `release_prep_reviewed_tree`,
  `release_prep_merge_commit`, `release_prep_merge_tree`;
- tag and Release: `tag_name`, `tag_object`, `peeled_commit`, `tag_tree`,
  `release_id`, `release_url`, `release_published_at`, `release_state`,
  `release_is_draft`, `release_is_prerelease`, `release_body_sha256`;
- immutable body identities: `tag_release_note_sha256`,
  `tag_changelog_section_sha256`;
- official source archive: `archive_filename`, `archive_bytes`,
  `archive_sha256`, `archive_safe_extraction`, `archive_git_free_smoke`;
- exact reviewed-head and exact-main hosted evidence: `reviewed_head_hosted_checks`
  and `exact_main_hosted_checks`;
- bounded non-claims: `non_claims`.

The owning `release_publication_contract.py` rejects premature publication
claims in the preparation state. In the published state it requires every
field above, checks the annotated-tag/merge identities and Release body hash,
requires `release_prep_reviewed_tree == release_prep_merge_tree`, requires the
two hosted-check groups to be successful on their respective exact SHAs,
verifies the frozen release note and changelog-section bytes, and rejects
mutable entrypoints that still call `v0.1.8` the last published stable release
or `v0.1.9` a preparation. The closeout PR identity and cleanup callback are
post-merge terminal evidence, not self-referential tracked-record fields.
