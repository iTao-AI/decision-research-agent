# P2A Controlled Verification Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Coding
> subagents are disabled by repository policy. Steps use checkbox (`- [ ]`)
> syntax for tracking.

**Goal:** Expose controlled Evidence verification operations and safely turn
changed verification snapshots into immutable artifact revisions that require a
fresh durable review before delivery.

**Architecture:** Rebuild the three one-review-per-run SQLite constraints,
introduce an explicit current publication row protected by a unique partial
index, and integrate verification decisions, deterministic artifact rebuild,
and review resolution through fenced application-database transactions. Reuse
the existing durable worker and LangGraph checkpoint gate; add no new workflow
engine or authority store.

**Tech Stack:** Python 3.11+, FastAPI 0.138, Pydantic 2.13, SQLite WAL,
LangGraph SQLite checkpointer, pytest, Docker Compose.

---

## Delivery Boundary

This plan implements P2A PR2 as one external PR with six sequential commits.

Included:

- review-table revision migration and exact schema verification;
- explicit revisioned publication state;
- deterministic Talent artifact rebuild from persisted snapshots;
- fresh review workflow per changed snapshot;
- atomic stale/current transitions;
- strict authenticated API;
- canonical Tool Client commands;
- runtime readiness, operator docs, migration recovery, and canary tests.

Excluded:

- real public-source proof, which remains PR3;
- network verification, DNS, browser automation, or LLM reviewer;
- claim editing or automatic research rerun;
- frontend or React work;
- Skills, Async Subagents, long-term memory authority, or Agent Server changes;
- RBAC, SSO, PostgreSQL, multiple replicas, or distributed workers;
- new legacy aliases or removal of existing compatibility identifiers.

## File Map

### Create

- `api/publication_models.py`
  - frozen publication contracts, stable IDs, status literals, cursor helpers,
    and finalization request.
- `api/publication_repository.py`
  - migration, publication schema, backfill, current-head queries, atomic stale
    helper, and finalization persistence.
- `api/publication_service.py`
  - deterministic load/build orchestration over persisted run inputs and one
    verification snapshot.
- `api/evidence_verification_api.py`
  - strict auth, bounded errors, list/detail/decision/finalize/health endpoints.
- `tests/unit/test_publication_models.py`
- `tests/unit/test_publication_migrations.py`
- `tests/unit/test_publication_repository.py`
- `tests/unit/test_publication_service.py`
- `tests/integration/test_evidence_verification_api.py`
- `tests/integration/test_revisioned_review_lifecycle.py`
- `tests/integration/test_evidence_verification_container.py`
- `docs/operations/evidence-verification-workflow.md`

### Modify

- `agent/talent_contracts.py`
  - add backward-compatible verification projection fields.
- `api/evidence_verification_repository.py`
  - stale the current publication and increment run state on accepted decisions.
- `api/talent_artifacts.py`
  - build revisioned artifacts from effective verification projections.
- `api/review_service.py`
  - accept mandatory deterministic triggers.
- `api/review_models.py`
  - add `superseded`, finalization fencing helpers, and revisioned segment use.
- `api/review_repository.py`
  - query exact/current revisions and resolve only current publications.
- `api/review_worker.py`
  - load the DecisionBrief bound to the claimed review/publication.
- `api/review_artifacts.py`
  - generate revision-aware reviewed artifact IDs.
- `api/review_config.py`
  - compose Evidence verification readiness with durable review readiness.
- `api/run_repository.py`
  - expose bounded current publication and current artifact projections.
- `api/run_migrations.py`
  - verify and back up/restore the PR2 schema.
- `api/server.py`
  - include the router and initialize readiness during lifespan.
- `tools/decision_research_agent_tool.py`
  - add canonical `evidence` commands and doctor output.
- `.env.example`
- `docker-compose.yml`
- `spec/api-contract.md`
- `spec/data-models.md`
- `docs/README.md`
- `docs/decisions/evidence-verification-authority.md`

### Do Not Modify

- `frontend/`
- LangSmith tracing configuration
- runtime Skills or subagent orchestration
- `agent/profile_agents.py`
- legacy Tool Client shim
- existing `DEEP_SEARCH_AGENT_*` resolver behavior
- `/health` service compatibility value
- benchmark fixture IDs or Talent profile ID

## Task 1: Add Revisioned Publication Schema and Safe Migration

**Files:**

- Create: `api/publication_models.py`
- Create: `api/publication_repository.py`
- Create: `tests/unit/test_publication_models.py`
- Create: `tests/unit/test_publication_migrations.py`
- Modify: `api/run_migrations.py`
- Modify: `tests/unit/test_run_migrations.py`

- [ ] **Step 1: Write publication contract RED tests**

Add tests for:

```python
def test_publication_id_binds_run_revision_and_snapshot():
    first = publication_id_for(
        run_id="run_1",
        revision=2,
        verification_snapshot_id="vsnap_1",
    )
    assert first == publication_id_for(
        run_id="run_1",
        revision=2,
        verification_snapshot_id="vsnap_1",
    )
    assert first != publication_id_for(
        run_id="run_1",
        revision=3,
        verification_snapshot_id="vsnap_1",
    )


def test_finalization_request_requires_non_negative_state_version():
    with pytest.raises(ValidationError):
        VerificationFinalizationRequest(expected_state_version=-1)
```

- [ ] **Step 2: Run contract tests and confirm RED**

Run:

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_publication_models.py -q
```

Expected: collection fails because `api.publication_models` does not exist.

- [ ] **Step 3: Implement frozen publication contracts**

Create these public types:

```python
PublicationStatus = Literal["review_required", "ready", "blocked", "stale"]


class PublicationContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class VerificationFinalizationRequest(PublicationContract):
    expected_state_version: int = Field(ge=0)


class PublicationRecord(PublicationContract):
    publication_id: str
    run_id: str
    revision: int = Field(ge=1)
    verification_snapshot_id: str
    review_id: str
    status: PublicationStatus
    is_current: bool
    artifact_ids: tuple[str, ...]
    content_hash: str
    supersedes_publication_id: str | None = None
    created_at: str
    resolved_at: str | None = None
    staled_at: str | None = None
```

Add deterministic `publication_id_for()`, opaque evidence cursor helpers, and
bounded ID validation using the repository's existing identifier pattern.

- [ ] **Step 4: Write migration RED tests**

Create fixtures with existing revision-one review data, then assert:

```python
def test_publication_migration_preserves_existing_review_rows(tmp_path):
    db_path = seed_revision_one_review_database(tmp_path)
    backup_path = str(tmp_path / "backup.db")
    before = snapshot_existing_review_rows(db_path)
    migrate_publication_with_backup(
        db_path=db_path,
        backup_path=backup_path,
    )
    after = snapshot_existing_review_rows(db_path)
    assert after == before


def test_migrated_schema_allows_two_review_revisions_for_one_run(tmp_path):
    seeded = seed_revision_one_review_database(tmp_path, return_ids=True)
    migrate_publication_with_backup(
        db_path=seeded.db_path,
        backup_path=str(tmp_path / "backup.db"),
    )
    insert_revision_two_bundle_workflow_and_resolution(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
    )
    assert load_review_revisions(seeded.db_path) == [1, 2]


def test_publication_partial_index_rejects_two_current_rows(tmp_path):
    seeded = seed_current_publication(tmp_path)
    with pytest.raises(sqlite3.IntegrityError):
        insert_second_current_publication(
            db_path=seeded.db_path,
            run_id=seeded.run_id,
        )


def test_failed_publication_migration_restores_backup(tmp_path, monkeypatch):
    db_path = seed_revision_one_review_database(tmp_path)
    backup_path = str(tmp_path / "backup.db")
    monkeypatch.setattr(
        publication_repository,
        "verify_publication_schema",
        lambda **_: (_ for _ in ()).throw(RuntimeError("forced")),
    )
    with pytest.raises(RuntimeError, match="forced"):
        migrate_publication_with_backup(
            db_path=db_path,
            backup_path=backup_path,
        )
    assert snapshot_database(db_path) == snapshot_database(backup_path)
```

- [ ] **Step 5: Run migration tests and confirm RED**

Run:

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_publication_migrations.py \
  tests/unit/test_run_migrations.py -q
```

Expected: failures for missing migration, unchanged unique constraints, and
missing `run_publications_v2`.

- [ ] **Step 6: Implement migration `006_revisioned_publication`**

Use:

```text
PUBLICATION_MIGRATION_VERSION = "006_revisioned_publication"
PUBLICATION_MIGRATION_CHECKSUM = "revisioned-publication-v1"
```

Implementation requirements:

1. call `init_evidence_verification_schema()` first;
2. return immediately when the exact marker and checksum already exist;
3. set `PRAGMA foreign_keys=OFF` before `BEGIN IMMEDIATE`;
4. create new review tables with revised constraints;
5. copy every column explicitly and verify row counts;
6. drop old tables and rename new tables into place;
7. recreate required indexes;
8. create `run_publications_v2` and its unique partial current index;
9. backfill deterministic revision-one snapshots/publications;
10. run `PRAGMA foreign_key_check`;
11. insert the migration marker;
12. commit and re-enable foreign keys; and
13. run exact schema verification.

Do not use `PRAGMA writable_schema`.

- [ ] **Step 7: Extend schema verification**

Verify:

- exact required tables and columns;
- migration checksum;
- unique `(run_id, revision)` indexes;
- unique partial current-publication index SQL;
- check constraints through stored table SQL;
- row counts after rebuild; and
- foreign keys.

- [ ] **Step 8: Run Task 1 GREEN tests**

Run:

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_publication_models.py \
  tests/unit/test_publication_migrations.py \
  tests/unit/test_run_migrations.py \
  tests/unit/test_review_migrations.py \
  tests/unit/test_evidence_verification_migrations.py -q
```

Expected: all pass.

- [ ] **Step 9: Commit Task 1**

```bash
git add \
  api/publication_models.py \
  api/publication_repository.py \
  api/run_migrations.py \
  tests/unit/test_publication_models.py \
  tests/unit/test_publication_migrations.py \
  tests/unit/test_run_migrations.py
git commit -m "feat(research): migrate revisioned publications"
```

## Task 2: Generalize Durable Review to Exact Revisions

**Files:**

- Modify: `api/review_models.py`
- Modify: `api/review_repository.py`
- Modify: `api/review_worker.py`
- Modify: `api/review_artifacts.py`
- Modify: `tests/unit/test_review_models.py`
- Modify: `tests/unit/test_review_repository.py`
- Modify: `tests/unit/test_review_worker.py`
- Modify: `tests/unit/test_review_artifacts.py`
- Create: `tests/integration/test_revisioned_review_lifecycle.py`

- [ ] **Step 1: Write multi-revision RED tests**

Cover:

```python
def test_review_projection_uses_current_publication_review(tmp_path):
    seeded = seed_two_publication_revisions(tmp_path)
    projection = get_review_projection(
        run_id=seeded.run_id,
        db_path=seeded.db_path,
    )
    assert projection["workflow"]["review_revision"] == 2


def test_review_detail_selects_decision_and_resolution_by_review_id(tmp_path):
    seeded = seed_two_resolved_revisions(tmp_path)
    first = get_review_detail(
        run_id=seeded.run_id,
        review_id=seeded.review_id_1,
        db_path=seeded.db_path,
    )
    second = get_review_detail(
        run_id=seeded.run_id,
        review_id=seeded.review_id_2,
        db_path=seeded.db_path,
    )
    assert first["decision"]["review_id"] == seeded.review_id_1
    assert second["decision"]["review_id"] == seeded.review_id_2


def test_post_review_segment_sequence_matches_review_revision(tmp_path):
    seeded = seed_revision_two_pending_workflow(tmp_path)
    claim = claim_review_workflow(
        db_path=seeded.db_path,
        worker_id="worker_1",
        lease_seconds=30,
    )
    segment = load_segment(
        db_path=seeded.db_path,
        segment_id=claim.post_review_segment_id,
    )
    assert segment["sequence"] == claim.review_revision


def test_superseded_workflow_is_not_claimed_or_decided(tmp_path):
    seeded = seed_superseded_workflow(tmp_path)
    assert claim_review_workflow(
        db_path=seeded.db_path,
        worker_id="worker_1",
        lease_seconds=30,
    ) is None
    with pytest.raises(ReviewConflict, match="review_superseded"):
        accept_review_decision(
            db_path=seeded.db_path,
            run_id=seeded.run_id,
            review_id=seeded.review_id,
            request=seeded.decision_request,
            actor_fingerprint="actor",
        )
```

- [ ] **Step 2: Run review tests and confirm RED**

Run:

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_review_models.py \
  tests/unit/test_review_repository.py \
  tests/unit/test_review_worker.py \
  tests/unit/test_review_artifacts.py \
  tests/integration/test_revisioned_review_lifecycle.py -q
```

Expected: failures from run-only queries, sequence `1`, fixed artifact IDs, and
missing `superseded`.

- [ ] **Step 3: Add exact revision semantics**

Required repository changes:

- add `superseded` to workflow/list status literals;
- select queue rows by workflow, but select run projection through
  `run_publications_v2.is_current=1`;
- select detail decision and resolution by exact `review_id`;
- load the source DecisionBrief through publication artifact IDs;
- generate post-review segment sequence from `review_revision`;
- resolve by exact `review_id`, not `run_id`;
- reject resolution unless the publication is current and
  `status='review_required'`; and
- keep legacy single-revision behavior when no publication row exists and the
  P2A feature is disabled.

- [ ] **Step 4: Make reviewed artifact IDs revision-aware**

Use:

```python
def reviewed_artifact_ids(revision: int) -> tuple[str, str]:
    if revision == 1:
        return (
            "decision-brief.reviewed.json",
            "decision-brief.reviewed.md",
        )
    return (
        f"decision-brief.r{revision}.reviewed.json",
        f"decision-brief.r{revision}.reviewed.md",
    )
```

`build_reviewed_artifacts()` receives the review/publication revision and never
overwrites another artifact row.

- [ ] **Step 5: Run Task 2 GREEN tests**

Run the Step 2 command.

Expected: all pass.

- [ ] **Step 6: Run existing durable compatibility tests**

```bash
../../.venv/bin/python -m pytest \
  tests/integration/test_durable_review_lifecycle.py \
  tests/integration/test_durable_review_restart.py \
  tests/integration/test_review_checkpoint_compatibility.py -q
```

Expected: all pass.

- [ ] **Step 7: Commit Task 2**

```bash
git add \
  api/review_models.py \
  api/review_repository.py \
  api/review_worker.py \
  api/review_artifacts.py \
  tests/unit/test_review_models.py \
  tests/unit/test_review_repository.py \
  tests/unit/test_review_worker.py \
  tests/unit/test_review_artifacts.py \
  tests/integration/test_revisioned_review_lifecycle.py
git commit -m "feat(review): support publication revisions"
```

## Task 3: Build Deterministic Snapshot-Bound Artifacts

**Files:**

- Create: `api/publication_service.py`
- Modify: `agent/talent_contracts.py`
- Modify: `api/talent_artifacts.py`
- Modify: `api/review_service.py`
- Create: `tests/unit/test_publication_service.py`
- Modify: `tests/unit/test_talent_artifacts.py`
- Modify: `tests/unit/test_talent_contracts.py`

- [ ] **Step 1: Write artifact rebuild RED tests**

Cover:

```python
def test_revisioned_artifacts_are_byte_stable_for_same_snapshot(tmp_path):
    persisted = seed_publication_inputs(tmp_path)
    first = build_publication_artifacts(
        connection=persisted.connection,
        run_id=persisted.run_id,
        snapshot_id=persisted.snapshot_id,
        revision=2,
    )
    second = build_publication_artifacts(
        connection=persisted.connection,
        run_id=persisted.run_id,
        snapshot_id=persisted.snapshot_id,
        revision=2,
    )
    assert first.brief_json == second.brief_json
    assert first.brief_markdown == second.brief_markdown


def test_revision_two_uses_new_ids_and_keeps_revision_one(tmp_path):
    persisted = seed_publication_inputs(tmp_path)
    result = build_publication_artifacts(
        connection=persisted.connection,
        run_id=persisted.run_id,
        snapshot_id=persisted.snapshot_id,
        revision=2,
    )
    assert result.artifact_ids == (
        "decision-brief.r2.json",
        "decision-brief.r2.md",
    )


def test_changed_snapshot_forces_fresh_review():
    review = build_review_bundle(
        run_id="run_1",
        findings=[],
        claims=[],
        evidence=[],
        confidence_threshold=0.6,
        revision=2,
        mandatory_triggers=("verification_snapshot_changed",),
    )
    assert review.required_before_delivery is True
    assert "verification_snapshot_changed" in review.triggers


def test_evidence_snapshot_exposes_origin_state_and_revision():
    snapshot = EvidenceSnapshot(
        evidence_id="ev_1",
        snippet="text",
        verification_status="unverified",
        verification_state="rejected",
        verification_origin="human",
        verification_revision=2,
    )
    assert snapshot.verification_state == "rejected"
```

- [ ] **Step 2: Run artifact tests and confirm RED**

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_publication_service.py \
  tests/unit/test_talent_artifacts.py \
  tests/unit/test_talent_contracts.py -q
```

Expected: failures for missing publication service and verification metadata.

- [ ] **Step 3: Extend backward-compatible Talent contracts**

Add optional/defaulted verification projection fields to `EvidenceSnapshot`.
Use `Field(exclude_if=lambda value: value is None)` so old revision-one
fixtures remain valid and serialize byte-for-byte without new null fields.

- [ ] **Step 4: Add deterministic persisted-input loader**

`publication_service.py` loads inside the caller's database transaction:

```text
research_runs_v2.scope_json
research_packets_v2.packet_json
evidence_entries_v2
evidence_verification_snapshots_v2.snapshot_json
```

It validates:

- Talent profile only;
- non-empty canonical packet state;
- exact Evidence IDs and fingerprints;
- every snapshot Evidence item resolves to the run; and
- no private verification fields enter the artifact.

- [ ] **Step 5: Generalize artifact construction**

`build_talent_artifacts()` gains explicit:

```python
revision: int = 1
verification_snapshot_id: str | None = None
verification_snapshot_hash: str | None = None
verification_by_evidence_id: Mapping[str, EffectiveEvidenceVerification] | None = None
mandatory_review_triggers: tuple[str, ...] = ()
```

Revision one keeps compatibility IDs. Later revisions use revisioned IDs.
`quality_summary` records publication and snapshot metadata.

- [ ] **Step 6: Run Task 3 GREEN tests**

Run the Step 2 command.

Expected: all pass and byte-stability assertions hold.

- [ ] **Step 7: Commit Task 3**

```bash
git add \
  agent/talent_contracts.py \
  api/publication_service.py \
  api/talent_artifacts.py \
  api/review_service.py \
  tests/unit/test_publication_service.py \
  tests/unit/test_talent_artifacts.py \
  tests/unit/test_talent_contracts.py
git commit -m "feat(research): rebuild snapshot bound artifacts"
```

## Task 4: Integrate Atomic Stale, Finalize, and Resolve Transitions

**Files:**

- Modify: `api/evidence_verification_repository.py`
- Modify: `api/publication_repository.py`
- Modify: `api/review_repository.py`
- Create: `tests/unit/test_publication_repository.py`
- Modify: `tests/unit/test_evidence_verification_repository.py`
- Modify: `tests/unit/test_review_repository.py`
- Modify: `tests/integration/test_revisioned_review_lifecycle.py`
- Modify: `tests/integration/test_durable_review_kill9.py`

- [ ] **Step 1: Write state-machine RED tests**

Cover:

```python
def test_new_decision_atomically_stales_current_publication(tmp_path):
    seeded = seed_current_publication_with_evidence(tmp_path)
    accepted = accept_verification_decision(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
        evidence_id=seeded.evidence_id,
        request=seeded.verification_request,
        actor_fingerprint="actor",
    )
    publication = get_publication(
        db_path=seeded.db_path,
        publication_id=seeded.publication_id,
    )
    run = get_run(db_path=seeded.db_path, run_id=seeded.run_id)
    workflow = get_review_detail(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
        review_id=seeded.review_id,
    )
    assert accepted.idempotent_replay is False
    assert publication.status == "stale"
    assert publication.is_current is False
    assert workflow["workflow"]["status"] == "superseded"
    assert run["delivery_status"] == "review_required"


def test_first_decision_adopts_then_stales_missing_baseline(tmp_path):
    seeded = seed_legacy_talent_run_without_publication(tmp_path)
    accept_verification_decision(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
        evidence_id=seeded.evidence_id,
        request=seeded.verification_request,
        actor_fingerprint="actor",
    )
    revision_one = get_publication_by_revision(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
        revision=1,
    )
    assert revision_one.status == "stale"
    assert "decision-brief.json" in revision_one.artifact_ids


def test_enabled_initial_run_seeds_baseline_publication(tmp_path):
    seeded = finalize_enabled_talent_run(tmp_path)
    publication = get_current_publication(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
    )
    assert publication.revision == 1
    assert publication.artifact_ids[0] == "decision-brief.json"


def test_idempotent_decision_replay_does_not_increment_run_twice(tmp_path):
    seeded = seed_current_publication_with_evidence(tmp_path)
    first = accept_verification_decision(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
        evidence_id=seeded.evidence_id,
        request=seeded.verification_request,
        actor_fingerprint="actor",
    )
    version = get_run(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
    )["state_version"]
    second = accept_verification_decision(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
        evidence_id=seeded.evidence_id,
        request=seeded.verification_request,
        actor_fingerprint="actor",
    )
    assert second.idempotent_replay is True
    assert get_run(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
    )["state_version"] == version


def test_changed_snapshot_creates_one_current_publication(tmp_path):
    seeded = seed_stale_publication_with_changed_snapshot(tmp_path)
    result = finalize_verification_publication(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
        expected_state_version=seeded.state_version,
    )
    assert result.publication.revision == 2
    assert result.publication.status == "review_required"
    assert count_current_publications(
        db_path=seeded.db_path,
        run_id=seeded.run_id,
    ) == 1


def test_stale_state_finalization_writes_nothing(tmp_path):
    seeded = seed_stale_publication_with_changed_snapshot(tmp_path)
    before = snapshot_publication_tables(seeded.db_path)
    with pytest.raises(PublicationConflict, match="stale_state_version"):
        finalize_verification_publication(
            db_path=seeded.db_path,
            run_id=seeded.run_id,
            expected_state_version=seeded.state_version - 1,
        )
    assert snapshot_publication_tables(seeded.db_path) == before


def test_old_review_approval_cannot_resolve_new_publication(tmp_path):
    seeded = seed_superseded_resumable_workflow(tmp_path)
    with pytest.raises(ReviewConflict, match="review_superseded"):
        resolve_review(
            db_path=seeded.db_path,
            workflow_id=seeded.workflow_id,
            worker_id=seeded.worker_id,
            expected_run_state_version=seeded.state_version,
            result=seeded.reviewed_result,
        )
```

- [ ] **Step 2: Run state-machine tests and confirm RED**

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_publication_repository.py \
  tests/unit/test_evidence_verification_repository.py \
  tests/unit/test_review_repository.py \
  tests/integration/test_revisioned_review_lifecycle.py -q
```

Expected: failures because decisions do not stale publications and finalization
does not create publication/workflow rows.

- [ ] **Step 3: Add connection-scoped snapshot helper**

Refactor PR1 snapshot logic into:

```python
def finalize_verification_snapshot_in_transaction(
    connection: sqlite3.Connection,
    *,
    run_id: str,
) -> VerificationSnapshotAcceptance:
    return _finalize_snapshot_for_connection(connection, run_id=run_id)
```

The existing public repository function opens its own transaction and delegates
to this helper, preserving PR1 behavior.

- [ ] **Step 4: Add atomic stale helper**

Implement:

```python
def stale_current_publication(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    now: str,
) -> str | None:
    return _stale_current_row_and_workflow(connection, run_id=run_id, now=now)
```

It updates publication, active workflow, and run state in the caller's
transaction. It returns the staled publication ID or `None`.

- [ ] **Step 5: Invoke stale helper after accepted decisions**

Call the helper only after a new decision row is inserted. Do not call it on
idempotent replay.

- [ ] **Step 6: Implement publication finalization**

`finalize_verification_publication()`:

- begins `IMMEDIATE`;
- fences run state;
- creates/reuses snapshot;
- returns current publication for an exact idempotent replay;
- repairs a missing workflow for current `review_required` revision;
- builds next artifacts/review/workflow for changed state;
- inserts all application rows atomically;
- increments run state once; and
- returns publication, snapshot, workflow, artifacts, and replay flag.

Before appending the first verification decision or finalizing an older run,
adopt the existing unversioned artifacts as baseline publication revision one.
If effective human decisions already exist, revision one is inserted stale and
the newly rebuilt current publication starts at revision two.

When Evidence verification is enabled during a new Talent run, seed baseline
publication revision one in the existing terminal run transaction.

- [ ] **Step 7: Bind review resolution to current publication**

`resolve_review()` must:

- load publication by exact review ID;
- reject stale/non-current publications;
- write reviewed artifact IDs for that publication revision;
- resolve by exact review ID;
- update publication and run status in the same transaction; and
- leave verification decisions unchanged.

- [ ] **Step 8: Add crash-window regression**

Extend kill-window coverage with a publication supersession stage. After
restart:

- no stale publication becomes ready;
- no superseded workflow is reclaimed;
- at most one current publication exists; and
- historical decisions remain queryable.

- [ ] **Step 9: Run Task 4 GREEN tests**

Run the Step 2 command plus:

```bash
../../.venv/bin/python -m pytest \
  tests/integration/test_durable_review_restart.py \
  tests/integration/test_durable_review_kill9.py -q
```

Expected: all pass.

- [ ] **Step 10: Commit Task 4**

```bash
git add \
  api/evidence_verification_repository.py \
  api/publication_repository.py \
  api/review_repository.py \
  tests/unit/test_publication_repository.py \
  tests/unit/test_evidence_verification_repository.py \
  tests/unit/test_review_repository.py \
  tests/integration/test_revisioned_review_lifecycle.py \
  tests/integration/test_durable_review_kill9.py
git commit -m "feat(research): enforce publication freshness"
```

## Task 5: Add Runtime Readiness and Authenticated API

**Files:**

- Create: `api/evidence_verification_api.py`
- Modify: `api/review_config.py`
- Modify: `api/server.py`
- Modify: `api/run_repository.py`
- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Create: `tests/integration/test_evidence_verification_api.py`
- Modify: `tests/unit/test_review_config.py`
- Modify: `tests/integration/test_run_api.py`
- Modify: `tests/integration/test_durable_review_lifecycle.py`

- [ ] **Step 1: Write runtime and auth-order RED tests**

Cover:

```python
def test_verification_is_disabled_by_default(client):
    response = client.get("/api/evidence-verifications/health")
    assert response.status_code == 404
    assert response.json()["code"] == "evidence_verification_disabled"


def test_verification_requires_durable_review_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION",
        "true",
    )
    monkeypatch.setenv(
        "DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL",
        "false",
    )
    with pytest.raises(
        ReviewConfigurationError,
        match="verification_review_runtime_required",
    ):
        validate_evidence_verification_runtime(
            review_runtime=ReviewRuntimeConfig(enabled=False),
            output_dir=tmp_path / "output",
        )


def test_auth_precedes_invalid_identity_and_missing_resource(client):
    response = client.get(
        "/api/runs/invalid id/evidence/verifications",
        headers={"X-API-Key": "wrong"},
    )
    assert response.status_code == 401


def test_finalize_rejects_stale_state_without_partial_rows(client, seeded_run):
    response = client.post(
        f"/api/runs/{seeded_run.run_id}/evidence/verification-snapshots",
        headers=auth,
        json={"expected_state_version": seeded_run.state_version - 1},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "stale_state_version"
```

- [ ] **Step 2: Run API tests and confirm RED**

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_review_config.py \
  tests/integration/test_evidence_verification_api.py \
  tests/integration/test_run_api.py \
  tests/integration/test_durable_review_lifecycle.py -q
```

Expected: route and runtime configuration failures.

- [ ] **Step 3: Add canonical-only feature flag**

Implement exact-true parsing for:

```text
DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION
```

Do not pass this key through the legacy environment resolver.

When enabled, startup requires the durable review runtime and PR2 schema to be
ready before starting the worker. Keep durable review validation in
`validate_review_runtime()` and add
`validate_evidence_verification_runtime()` as the composed P2A check.

- [ ] **Step 4: Implement bounded API models and errors**

Preserve the existing result-first error envelope:

```json
{
  "code": "verification_revision_conflict",
  "problem": "The evidence verification revision changed.",
  "cause": "expected_revision is stale.",
  "fix": "Fetch the evidence detail and retry with its current revision.",
  "retryable": true,
  "run_id": "run_example",
  "request_id": "request_example"
}
```

Authentication order:

1. feature flag;
2. `API_SECRET` configuration;
3. `X-API-Key`;
4. bounded path/query identity;
5. content type and request body;
6. resource lookup and repository operation.

- [ ] **Step 5: Implement list, detail, decision, finalize, and health routes**

Use `asyncio.to_thread()` for SQLite repository calls.

List:

- deterministic `evidence_id` ordering;
- limit `1..100`;
- opaque keyset cursor;
- no reason note or private audit fields.

Detail:

- exact preflight and effective state;
- bounded immutable decision history;
- reason notes allowed;
- actor/request hash omitted.

Decision:

- synchronous acceptance;
- stable conflict mapping;
- replay flag returned.

Finalize:

- requires JSON body with `expected_state_version`;
- checks app readiness before persistence;
- returns publication/review identity and replay state.

- [ ] **Step 6: Add current run projection**

When a publication exists, `get_run()` adds:

```python
{
    "current_publication": {
        "publication_id": "publication_example",
        "revision": 2,
        "status": "ready",
        "artifact_ids": ["decision-brief.r2.reviewed.json"],
    },
    "current_artifacts": [
        {
            "artifact_id": "decision-brief.r2.reviewed.json",
            "kind": "decision_brief_reviewed_json",
        }
    ],
    "verification_summary": {
        "state_counts": {"verified": 3, "rejected": 1},
        "origin_counts": {"human": 4},
        "snapshot_hash": "a" * 64,
    },
}
```

Keep the existing historical `artifacts` list.

- [ ] **Step 7: Run Task 5 GREEN tests**

Run the Step 2 command.

Expected: all pass.

- [ ] **Step 8: Commit Task 5**

```bash
git add \
  api/evidence_verification_api.py \
  api/review_config.py \
  api/server.py \
  api/run_repository.py \
  .env.example \
  docker-compose.yml \
  tests/unit/test_review_config.py \
  tests/integration/test_evidence_verification_api.py \
  tests/integration/test_run_api.py \
  tests/integration/test_durable_review_lifecycle.py
git commit -m "feat(research): expose controlled verification api"
```

## Task 6: Add CLI, Operations, Contracts, and End-to-End Verification

**Files:**

- Modify: `tools/decision_research_agent_tool.py`
- Modify: `tests/unit/test_decision_research_agent_tool.py`
- Create: `tests/integration/test_evidence_verification_container.py`
- Create: `docs/operations/evidence-verification-workflow.md`
- Modify: `spec/api-contract.md`
- Modify: `spec/data-models.md`
- Modify: `docs/decisions/evidence-verification-authority.md`
- Modify: `docs/README.md`

- [ ] **Step 1: Write CLI RED tests**

Cover:

```python
def test_evidence_verify_requires_explicit_confirmation():
    assert main([
        "evidence",
        "verify",
        "--run-id",
        "run_1",
        "--evidence-id",
        "ev_1",
    ]) == 1


def test_evidence_reject_reason_file_is_bounded_and_not_truncated(tmp_path):
    path = tmp_path / "reason.txt"
    path.write_text("x" * 1000 + "\nextra", encoding="utf-8")
    assert main([
        "evidence",
        "reject",
        "--run-id",
        "run_1",
        "--evidence-id",
        "ev_1",
        "--reason-code",
        "content_mismatch",
        "--reason-file",
        str(path),
    ]) == 1


def test_verification_id_is_stable_and_content_scoped():
    first = stable_verification_id(
        run_id="run_1",
        evidence_id="ev_1",
        evidence_fingerprint="a" * 64,
        expected_revision=0,
        action="verify",
        reason_code=None,
        reason_note=None,
    )
    assert first == stable_verification_id(
        run_id="run_1",
        evidence_id="ev_1",
        evidence_fingerprint="a" * 64,
        expected_revision=0,
        action="verify",
        reason_code=None,
        reason_note=None,
    )
    assert first != stable_verification_id(
        run_id="run_1",
        evidence_id="ev_1",
        evidence_fingerprint="a" * 64,
        expected_revision=0,
        action="reject",
        reason_code="content_mismatch",
        reason_note="mismatch",
    )


def test_evidence_finalize_uses_current_run_state_version(mock_server):
    mock_server.queue_json({"run_id": "run_1", "state_version": 5})
    mock_server.queue_json({"publication_id": "publication_2"})
    result = finalize_evidence_verification(
        run_id="run_1",
        config=mock_server.config,
    )
    posted_json = mock_server.requests[-1].json
    assert posted_json == {"expected_state_version": 5}
    assert result["publication_id"] == "publication_2"
```

- [ ] **Step 2: Run CLI tests and confirm RED**

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_decision_research_agent_tool.py -q
```

Expected: parser and command failures.

- [ ] **Step 3: Implement canonical `evidence` commands**

Add:

```text
evidence list --run-id
evidence show --run-id --evidence-id
evidence verify --run-id --evidence-id --confirm-source-match
evidence reject --run-id --evidence-id --reason-code --reason-file|--reason-stdin
evidence finalize --run-id
```

Refactor the existing bounded reason reader into a shared bounded text helper.
Keep current review CLI behavior unchanged.

- [ ] **Step 4: Extend doctor**

Call `/api/evidence-verifications/health`.

- `404 evidence_verification_disabled` -> `disabled`;
- ready response -> `ok`;
- any other structured failure -> `failed`.

- [ ] **Step 5: Write synthetic Docker canary**

The canary uses server-bundled deterministic test data and performs:

1. start backend with durable review and Evidence verification enabled;
2. create or seed one Talent run;
3. list Evidence;
4. verify one exact fingerprint;
5. finalize the changed snapshot;
6. wait for `waiting_decision`;
7. approve the new review;
8. wait for resolution;
9. assert one current `ready` publication;
10. assert revision-one artifacts still exist;
11. assert revision-two reviewed artifacts exist; and
12. restart the backend and assert the same current publication remains.

No network source lookup is allowed.

- [ ] **Step 6: Update operator documentation**

Document:

- enablement prerequisites;
- doctor output;
- list/show/verify/reject/finalize commands;
- bounded meaning of `human_verified`;
- publication and review states;
- stale/superseded behavior;
- backup/migration procedure;
- restart recovery;
- rollback by disabling the Evidence flag;
- manual recovery boundaries; and
- explicit non-goals.

- [ ] **Step 7: Update API, data-model, and ADR contracts**

Required corrections:

- one run may now have multiple review revisions;
- correction does not require a new run when only verification authority and
  derived publication change;
- collected Evidence and ResearchPackets remain immutable;
- old review decisions remain historical but cannot approve a new publication;
- current delivery requires current publication status `ready`; and
- approval still does not grant Evidence verification.

- [ ] **Step 8: Run focused verification**

```bash
../../.venv/bin/python -m pytest \
  tests/unit/test_publication_models.py \
  tests/unit/test_publication_migrations.py \
  tests/unit/test_publication_repository.py \
  tests/unit/test_publication_service.py \
  tests/unit/test_evidence_verification_repository.py \
  tests/unit/test_review_repository.py \
  tests/unit/test_review_worker.py \
  tests/unit/test_decision_research_agent_tool.py \
  tests/integration/test_evidence_verification_api.py \
  tests/integration/test_revisioned_review_lifecycle.py -q
```

Expected: all pass.

- [ ] **Step 9: Run full backend suite**

```bash
../../.venv/bin/python -m pytest -q
```

Expected: all pass; record the actual count and warnings.

- [ ] **Step 10: Re-run durable HITL gate**

```bash
../../.venv/bin/python scripts/durable_hitl_gate_runner.py \
  --output docs/evidence/durable-hitl-gate-report.json
```

Expected:

```text
status=PASS
expected=13
passed=13
failed=[]
```

- [ ] **Step 11: Run Docker canary when Docker is available**

```bash
../../.venv/bin/python -m pytest \
  tests/integration/test_evidence_verification_container.py -q
```

Expected: pass without skip when Docker is available. If Docker is unavailable,
record the exact reason; do not claim container verification.

- [ ] **Step 12: Check diff and feature defaults**

```bash
git diff --check
rg -n "DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION" \
  .env.example docker-compose.yml
rg -n "DEEP_SEARCH_AGENT_.*EVIDENCE|deep-search-agent.*verification" \
  api tools docs spec .env.example docker-compose.yml
```

Expected:

- diff check passes;
- canonical flag defaults to `false`;
- no new legacy Evidence verification identifier exists.

- [ ] **Step 13: Commit Task 6**

```bash
git add \
  tools/decision_research_agent_tool.py \
  tests/unit/test_decision_research_agent_tool.py \
  tests/integration/test_evidence_verification_container.py \
  docs/operations/evidence-verification-workflow.md \
  spec/api-contract.md \
  spec/data-models.md \
  docs/decisions/evidence-verification-authority.md \
  docs/README.md \
  docs/evidence/durable-hitl-gate-report.json
git commit -m "docs(research): document verification operations"
```

## Final Review Handoff

The execution window must return:

- branch and worktree;
- base and HEAD commits;
- per-task RED/GREEN evidence;
- focused and full-suite results;
- durable gate result;
- Docker canary result or exact skip reason;
- `git diff --check` result;
- feature-default evidence;
- changed file list;
- confirmation that no frontend, legacy alias expansion, Skills, Async
  Subagents, LLM verification, or real-source proof was added; and
- clean worktree with no push or PR.

An independent review window then performs one authoritative pre-PR review
against:

- this plan;
- the parent P2A design;
- `docs/decisions/evidence-verification-authority.md`;
- the full branch diff; and
- actual verification evidence.

Findings return to the execution window for targeted fixes. Repeat full review
only if fixes materially change schema, authority, state-machine, or API
boundaries.
