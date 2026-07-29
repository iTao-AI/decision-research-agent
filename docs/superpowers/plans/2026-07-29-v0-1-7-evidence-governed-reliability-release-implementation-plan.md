# Decision Research Agent v0.1.7 Evidence-Governed Reliability and Recovery Implementation Plan

Status: Approved by the user for implementation-plan landing. Implementation
and every external publication action remain separately gated.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Do not use subagent-driven development or parallel lanes: Phase B depends on the reviewed and merged Phase A identity, and both phases touch shared release-truth files.

**Goal:** First make the fixed Loop verifier compatible with an immutable historical `v0.1.6` record, then publish the already-merged post-`v0.1.6` reliability and recovery surface as a coherent, provider-free `v0.1.7` source release.

**Architecture:** Phase A is an evaluation/proof-only compatibility bridge. It changes the historical release selector and its public projection in a dedicated PR, while preserving the selector argument vector, profile binding, canonical cases, episode decisions, runtime, dependencies, and version. Phase B starts only from merged Phase A `main`; it changes release identity and current public truth in a second PR, then uses separate human gates for merge, annotated tag, GitHub Release, and archive observation.

**Tech Stack:** Python 3.11, Pydantic 2.13.4, pytest 9.0.3, pytest-asyncio 1.4.0, deterministic JSON/Markdown Loop artifacts, Node/npm frontend metadata, Git/GitHub Actions, Docker Compose, GitHub Releases.

## Global Constraints

- Approved spec: `docs/superpowers/specs/2026-07-29-v0-1-7-evidence-governed-reliability-release-design.md`, SHA-256 `c01d47f2652160ede12b5c25ed98cabfc1fdabd5e57e94ffd82289713982743c`.
- Original planning baseline: clean `main@8064a33bec6dfb403149e056a373f074c2cea409`.
- Phase A and Phase B are separate branches, reviews, PRs, exact-head CI gates, and squash merges.
- Phase B must start from the exact merged Phase A `main`; it must not be implemented on the Phase A feature branch.
- Keep `scripts.evidence_gated_loop_profiles.STRICT_ARGV`, `PROFILE_REGISTRY`, every `benchmarks/evidence-gated-loop-v1/cases/*.json` byte, every episode, verdict, consumer proof, and `release_disposition` unchanged.
- Phase A may change only offline verification tests/contracts, generated Loop registry/report projections, current public-neutral documentation, and this spec/plan index.
- Phase B may change only release identity, release notes, current public truth, and release/documentation tests.
- Do not change runtime Agent behavior, API, database code, migration `010`, dependency pins, Evidence/strict-citation schemas, downstream fixtures, or any consumer repository.
- Python pins remain exactly those in `constraints.txt`; do not resolve, upgrade, or normalize the known `ragflow-sdk 0.13.0` metadata declaration against `pytest==9.0.3`.
- No provider/model/tool request, credential read, `observe-live`, additional governed provider attempt, remote LangSmith tracing, deployment, or hosted service.
- A missing task-local pinned environment is a hard `DRA_PINNED_ENVIRONMENT_REQUIRED` stop. Environment creation or installation requires separate explicit authorization.
- Docker execution requires a fresh engine inventory, a unique task-owned Compose project, bounded resources, retained-data review, and exact cleanup. Never run global prune.
- Push, PR creation, merge, annotated tag, GitHub Release, Release edits, and cleanup are distinct external gates and require explicit authorization.
- PR title and body are Simplified Chinese; repository documents remain public-neutral and follow the existing English technical-document style.
- Historical release notes `v0.1.0` through `v0.1.6` remain byte-identical.
- A published tag is never force-moved or silently deleted.

### Pinned Environment Verification

Phase A and Phase B use this same deterministic gate after confirming
`.venv/bin/python` exists and reports Python 3.11:

```bash
.venv/bin/python - <<'PY'
import importlib.metadata as metadata
from pathlib import Path

from packaging.utils import canonicalize_name

expected: dict[str, str] = {}
for raw in Path("constraints.txt").read_text(encoding="utf-8").splitlines():
    line = raw.split("#", 1)[0].strip()
    if not line:
        continue
    name, separator, version = line.partition("==")
    assert separator == "==" and name and version and "==" not in version
    normalized = canonicalize_name(name)
    assert normalized not in expected
    expected[normalized] = version

assert len(expected) == 96, len(expected)
actual = {
    name: metadata.version(name)
    for name in expected
}
assert actual == expected, {
    name: (expected[name], actual.get(name))
    for name in expected
    if actual.get(name) != expected[name]
}
print("DRA_PINNED_ENVIRONMENT_OK")
PY
```

Then run `uv pip check` only as a separately recorded metadata diagnostic.
The one accepted diagnostic is the already reviewed
`ragflow-sdk 0.13.0` declaration of `pytest<9` against the deliberate
`pytest==9.0.3` no-deps lock. A second incompatibility, missing distribution,
version drift, import failure, or test failure blocks; the execution window
does not edit pins or enable installation to make this gate pass.

---

## File Structure

### Phase A — Release-Lineage Compatibility Bridge

- Modify: `tests/unit/test_v0_1_6_release_metadata.py`
  - Become a pure immutable historical `v0.1.6` authority: release-note,
    changelog-section, earlier-note hashes, and retained release contracts only.
  - Remove mutable root-version, `[Unreleased]`, README, SECURITY, and current
    discovery assertions; those remain owned by
    `tests/unit/test_release_metadata.py`.
  - Retain the exact pytest selector name used by `STRICT_ARGV`.
- Modify: `scripts/evidence_gated_loop_contracts.py`
  - Replace only the mutable-current-release non-claim with immutable historical release wording.
- Modify: `benchmarks/evidence-gated-loop-v1/registry.json`
  - Mirror the required non-claim; no case/profile/path change.
- Regenerate: `docs/evidence/evidence-gated-loop-kernel-v1.json`
- Regenerate: `docs/evidence/evidence-gated-loop-kernel-v1.md`
  - Project the new registry/non-claim while preserving cases, verification results, summary, and limits.
- Modify: `README.md`
- Modify: `README_CN.md`
- Modify: `docs/reference/evidence-gated-loop-kernel.md`
  - Publish equivalent immutable-selector wording.
- Modify: `CHANGELOG.md`
  - Add one bounded `[Unreleased]` compatibility-bridge entry.
- Modify: `docs/superpowers/README.md`
  - Link the approved release spec and implementation plan.
- Modify: `tests/unit/test_public_truth_documentation.py`
- Modify: `tests/unit/test_documentation_contracts.py`
  - Lock the equivalent public wording and Superpowers navigation.

### Phase B — v0.1.7 Release Preparation

- Modify: `VERSION`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
  - Set only release root identity to `0.1.7`.
- Create: `docs/releases/v0.1.7.md`
  - Own the release surface, compatibility, rollback, verification, and non-claims.
- Modify: `CHANGELOG.md`
  - Move the completed post-`v0.1.6` surface under `[0.1.7] - 2026-07-29`.
- Modify: `README.md`
- Modify: `README_CN.md`
- Modify: `SECURITY.md`
- Modify: `docs/README.md`
- Modify: `docs/operations/run-execution-recovery.md`
- Modify: `docs/reference/observation-contract.md`
- Modify: `docs/reference/evidence-gated-loop-kernel.md`
  - Replace unreleased/current-hold presentation with release-preparation truth while preserving historical `hold`.
- Modify: `tests/unit/test_release_metadata.py`
  - Point current-release assertions at `v0.1.7`; retain historical contracts.
- Create: `tests/unit/test_v0_1_7_release_metadata.py`
  - Own the complete new release contract and historical-note hashes.
- Modify: `tests/unit/test_public_truth_documentation.py`
- Modify: `tests/unit/test_documentation_contracts.py`
  - Lock current release presentation, migration/rollback, and non-claims.

---

### Task 1: Freeze the Immutable v0.1.6 Historical Selector

**Files:**
- Modify: `tests/unit/test_v0_1_6_release_metadata.py`
- Test: `tests/unit/test_v0_1_6_release_metadata.py`

**Interfaces:**
- Consumes: `Path`, `sha256`, `docs/releases/v0.1.6.md`, and the `[0.1.6]` changelog section.
- Produces: `_assert_v0_1_6_historical_identity(project_root: Path) -> None`; the existing public selector `test_v0_1_6_version_identity_is_consistent()` delegates to it.
- Removes: all mutable-current assertions from this historical selector file.
  Existing generic current-release tests in `tests/unit/test_release_metadata.py`
  continue to own root version, `[Unreleased]`, README, SECURITY, and discovery
  truth during Phase A.

- [ ] **Step 0: Freeze the exact Phase A implementation base**

After the approved spec and plan are mechanically landed, verify a clean
worktree and record:

```bash
test -z "$(git status --short)"
PHASE_A_IMPLEMENTATION_BASE="$(git rev-parse HEAD)"
test -n "$PHASE_A_IMPLEMENTATION_BASE"
```

Every Phase A implementation-only scope check uses this exact commit. The PR
base remains original `main@8064a33bec6dfb403149e056a373f074c2cea409`,
which intentionally includes the approved spec and plan in the final PR diff.

- [ ] **Step 1: Record immutable input identities**

Run:

```bash
test "$(sha256sum docs/releases/v0.1.6.md | cut -d' ' -f1)" = \
  "0cb73ea51e8aae8d4e997a0225a31439dbc11b2977692d3510b8d33d1963552e"

python - <<'PY'
from hashlib import sha256
from pathlib import Path

text = Path("CHANGELOG.md").read_text(encoding="utf-8")
start = "## [0.1.6] - 2026-07-24"
end = "## [0.1.5] - 2026-07-18"
section = start + text.split(start, 1)[1].split(end, 1)[0]
assert sha256(section.encode("utf-8")).hexdigest() == (
    "2dc1e44fe1d571381cb15bb41f21584d0087b9896436c0876efc347294b437c9"
)
PY
```

Expected: exit `0`.

- [ ] **Step 2: Add RED tests for a later current version and historical-byte mutation**

Add `shutil` and these tests without yet defining `_assert_v0_1_6_historical_identity`:

```python
def _copy_v0_1_6_history(target: Path) -> None:
    releases = target / "docs" / "releases"
    releases.mkdir(parents=True)
    shutil.copy2(V016_RELEASE_NOTES, releases / "v0.1.6.md")
    shutil.copy2(PROJECT_ROOT / "CHANGELOG.md", target / "CHANGELOG.md")
    (target / "VERSION").write_text("0.1.7\n", encoding="utf-8")
    frontend = target / "frontend"
    frontend.mkdir()
    (frontend / "package.json").write_text(
        '{"version":"0.1.7"}\n',
        encoding="utf-8",
    )
    (frontend / "package-lock.json").write_text(
        '{"version":"0.1.7","packages":{"":{"version":"0.1.7"}}}\n',
        encoding="utf-8",
    )


def test_v0_1_6_selector_accepts_later_current_release_identity(
    tmp_path: Path,
) -> None:
    _copy_v0_1_6_history(tmp_path)
    _assert_v0_1_6_historical_identity(tmp_path)


def test_v0_1_6_selector_rejects_historical_release_note_byte_drift(
    tmp_path: Path,
) -> None:
    _copy_v0_1_6_history(tmp_path)
    notes = tmp_path / "docs" / "releases" / "v0.1.6.md"
    notes.write_text(
        notes.read_text(encoding="utf-8").replace(
            "# Decision Research Agent v0.1.6",
            "# Decision Research Agent v0.1.6 drifted",
            1,
        ),
        encoding="utf-8",
    )
    with pytest.raises(AssertionError):
        _assert_v0_1_6_historical_identity(tmp_path)
```

- [ ] **Step 3: Run the new tests and confirm RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_v0_1_6_release_metadata.py::test_v0_1_6_selector_accepts_later_current_release_identity \
  tests/unit/test_v0_1_6_release_metadata.py::test_v0_1_6_selector_rejects_historical_release_note_byte_drift
```

Expected: both tests fail with `NameError: name '_assert_v0_1_6_historical_identity' is not defined`.

- [ ] **Step 4: Implement the immutable historical identity helper**

Remove the now-unused `json` import. Add:

```python
V016_RELEASE_NOTES_SHA256 = (
    "0cb73ea51e8aae8d4e997a0225a31439dbc11b2977692d3510b8d33d1963552e"
)
V016_CHANGELOG_SECTION_SHA256 = (
    "2dc1e44fe1d571381cb15bb41f21584d0087b9896436c0876efc347294b437c9"
)


def _assert_v0_1_6_historical_identity(project_root: Path) -> None:
    notes = project_root / "docs" / "releases" / "v0.1.6.md"
    changelog = _read(project_root / "CHANGELOG.md")
    start = f"## [0.1.6] - {RELEASE_DATE}"
    end = "## [0.1.5] - 2026-07-18"
    section = start + changelog.split(start, 1)[1].split(end, 1)[0]

    assert sha256(notes.read_bytes()).hexdigest() == V016_RELEASE_NOTES_SHA256
    assert sha256(section.encode("utf-8")).hexdigest() == (
        V016_CHANGELOG_SECTION_SHA256
    )
    assert notes.read_text(encoding="utf-8").startswith(
        "# Decision Research Agent v0.1.6\n\n"
        f"Release preparation date: {RELEASE_DATE}."
    )
```

Replace the existing selector body with:

```python
def test_v0_1_6_version_identity_is_consistent() -> None:
    _assert_v0_1_6_historical_identity(PROJECT_ROOT)
```

The selector name remains exact because `STRICT_ARGV` owns that argument vector.

In the same edit, remove:

- `V016_PUBLIC_RELEASE_CORPUS`;
- the root `VERSION`, frontend package, and lockfile assertions;
- mutable `[Unreleased]` and privacy-safe-observation placement assertions;
- `test_v0_1_6_release_discovery_and_security_truth_are_current`;
- imports used only by those deleted assertions.

Keep every immutable `v0.1.6` release-note section assertion, earlier release
note hash, v0.1.5-and-earlier changelog suffix hash, alias-retirement contract,
maintenance contract, and premature-publication non-claim that is scoped to the
immutable v0.1.6 release note itself. Do not move mutable-current truth back
into this file later in Phase B.

- [ ] **Step 5: Run focused GREEN and the complete historical release file**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_v0_1_6_release_metadata.py
```

Expected: every test passes.

- [ ] **Step 6: Prove the profile argument vector and current version are unchanged**

Run:

```bash
git diff --exit-code HEAD -- scripts/evidence_gated_loop_profiles.py VERSION \
  frontend/package.json frontend/package-lock.json constraints.txt

PYTHON_DOTENV_DISABLED=1 .venv/bin/python - <<'PY'
from scripts.evidence_gated_loop_profiles import STRICT_ARGV

assert STRICT_ARGV[-1] == (
    "tests/unit/test_v0_1_6_release_metadata.py::"
    "test_v0_1_6_version_identity_is_consistent"
)
PY
```

Expected: exit `0`.

- [ ] **Step 7: Commit the historical selector correction**

```bash
git add tests/unit/test_v0_1_6_release_metadata.py
git commit -m "test(release): freeze v0.1.6 historical identity"
```

---

### Task 2: Bind the Immutable Selector Through Public and Canonical Loop Truth

**Files:**
- Modify: `scripts/evidence_gated_loop_contracts.py:32-42`
- Modify: `benchmarks/evidence-gated-loop-v1/registry.json`
- Regenerate: `docs/evidence/evidence-gated-loop-kernel-v1.json`
- Regenerate: `docs/evidence/evidence-gated-loop-kernel-v1.md`
- Modify: `README.md:309-341`
- Modify: `README_CN.md:347-375`
- Modify: `docs/reference/evidence-gated-loop-kernel.md`
- Modify: `CHANGELOG.md:5-8`
- Modify: `docs/superpowers/README.md:22-30`
- Modify: `tests/unit/test_public_truth_documentation.py`
- Modify: `tests/unit/test_documentation_contracts.py`

**Interfaces:**
- Consumes: the existing `REQUIRED_NON_CLAIMS` closed tuple and deterministic Loop build.
- Produces: this exact required sentence in every current projection:
  `The v0.1.6 selector verifies only the immutable v0.1.6 release record; it does not execute historical release behavior.`
- Produces: a narrow reference classification for compatible verifier
  maintenance. The profile may retain version `1` only because profile ID,
  argument vector, timeout, coverage, failure code, episode binding, intended
  strict-consumer invariant, and canonical case bytes remain unchanged; the
  repository commit still identifies the exact implementation.

- [ ] **Step 1: Capture protected case, profile, version, dependency, and CI hashes**

Run:

```bash
sha256sum \
  benchmarks/evidence-gated-loop-v1/cases/context-resolver-projection.json \
  benchmarks/evidence-gated-loop-v1/cases/evaluation-sensitivity.json \
  benchmarks/evidence-gated-loop-v1/cases/strict-citation-consumer.json \
  constraints.txt .github/workflows/ci.yml
```

Expected hashes:

```text
9d51fb053848e52a1e76499fe0002cc6dfb7d02f2485d937ae5773e9447abbfc  benchmarks/evidence-gated-loop-v1/cases/context-resolver-projection.json
f728d745eff37a8e83d7b5fd0f8430dfd93579cc10d47ea609d96966cc5fc4af  benchmarks/evidence-gated-loop-v1/cases/evaluation-sensitivity.json
55a2b855f4e3128ef94fb370530b4816882118e29feba065ff48f3def57a8eea  benchmarks/evidence-gated-loop-v1/cases/strict-citation-consumer.json
d8ddec45f8d50210458651e453d68beafa916c6358d1d47a71ac8f72db75295f  constraints.txt
8eefc4b077d8c24eaf5cf3328790b675b204a38476700e2065b6c6df3ae6ee0e  .github/workflows/ci.yml
```

- [ ] **Step 2: Add RED public-truth tests**

Add:

```python
def test_loop_selector_uses_immutable_v0_1_6_release_record() -> None:
    exact = (
        "The v0.1.6 selector verifies only the immutable v0.1.6 release "
        "record; it does not execute historical release behavior."
    )
    old = "verifies current release metadata only"
    english = _read("README.md")
    reference = _read("docs/reference/evidence-gated-loop-kernel.md")
    markdown = _read("docs/evidence/evidence-gated-loop-kernel-v1.md")
    registry = _read("benchmarks/evidence-gated-loop-v1/registry.json")
    report = _read("docs/evidence/evidence-gated-loop-kernel-v1.json")

    for text in (english, reference, markdown, registry, report):
        assert exact in text
        assert old not in text

    chinese = _read("README_CN.md")
    assert (
        "v0.1.6 selector 只验证不可变的 v0.1.6 release record，"
        "不执行历史 release 行为。"
    ) in chinese
    assert "只验证当前 release metadata" not in chinese


def test_loop_reference_bounds_compatible_verifier_maintenance() -> None:
    reference = _read("docs/reference/evidence-gated-loop-kernel.md")
    normalized = " ".join(reference.split())
    for phrase in (
        "compatible verifier maintenance",
        "accidental dependency on mutable repository-root release identity",
        "profile ID/version, argument vector, timeout, coverage, failure code, "
        "episode binding, intended strict-consumer invariant, and canonical "
        "case bytes remain unchanged",
        "repository commit continues to distinguish the exact implementation",
        "must land before the evaluated release candidate",
    ):
        assert phrase in normalized
    assert (
        "Any change to the intended invariant or listed profile contract "
        "requires a profile-version and case-binding review."
    ) in normalized
```

Extend the Superpowers documentation contract to require:

```python
for target in (
    "specs/2026-07-29-v0-1-7-evidence-governed-reliability-release-design.md",
    "plans/2026-07-29-v0-1-7-evidence-governed-reliability-release-implementation-plan.md",
):
    assert target in superpowers
```

- [ ] **Step 3: Run focused tests and confirm RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_public_truth_documentation.py::test_loop_selector_uses_immutable_v0_1_6_release_record \
  tests/unit/test_documentation_contracts.py
```

Expected: the new immutable-selector and navigation assertions fail against the old wording/index.

- [ ] **Step 4: Change the closed non-claim and current public wording**

In `scripts/evidence_gated_loop_contracts.py`, replace only the fourth required non-claim with:

```python
"The v0.1.6 selector verifies only the immutable v0.1.6 release record; "
"it does not execute historical release behavior.",
```

Use the same English sentence in:

- `benchmarks/evidence-gated-loop-v1/registry.json`
- `README.md`
- `docs/reference/evidence-gated-loop-kernel.md`

Use this equivalent sentence in `README_CN.md`:

```text
v0.1.6 selector 只验证不可变的 v0.1.6 release record，不执行历史 release 行为。
```

In `docs/reference/evidence-gated-loop-kernel.md`, add this bounded maintenance
rule next to the existing profile-version table:

```markdown
Correcting the v0.1.6 selector is compatible verifier maintenance: it removes
an accidental dependency on mutable repository-root release identity while the
profile ID/version, argument vector, timeout, coverage, failure code, episode
binding, intended strict-consumer invariant, and canonical case bytes remain
unchanged. The repository commit continues to distinguish the exact
implementation. This maintenance must land before the evaluated release
candidate. Any change to the intended invariant or listed profile contract
requires a profile-version and case-binding review.
```

This is not a general exception to the version table. Do not add a new profile
version, alter `PROFILE_REGISTRY`, change episode bindings, or reinterpret case
meaning in this compatibility bridge.

Add this `[Unreleased]` entry:

```markdown
### Immutable v0.1.6 release-lineage selector

- Corrected the fixed strict-consumer profile's final selector to verify the
  immutable v0.1.6 release record rather than requiring the mutable repository
  root to remain at version 0.1.6.
- The selector argument vector, profile binding, canonical cases, episode
  decisions, runtime, dependencies, and release version remain unchanged.
```

Add this section to `docs/superpowers/README.md` before the crash-recovery records:

```markdown
## Current v0.1.7 Release Records

- [Approved design](specs/2026-07-29-v0-1-7-evidence-governed-reliability-release-design.md)
- [Approved implementation plan](plans/2026-07-29-v0-1-7-evidence-governed-reliability-release-implementation-plan.md)

Phase A and Phase B are separately reviewed release records. Current code,
tests, release notes, Git identities, hosted checks, and public Release state
remain authoritative.
```

- [ ] **Step 5: Regenerate the canonical report into task-owned paths**

Run:

```bash
LOOP_TMP="$(mktemp -d)"
PYTHON_DOTENV_DISABLED=1 .venv/bin/python \
  scripts/evidence_gated_loop_gate.py build \
  --json-output "$LOOP_TMP/evidence-gated-loop-kernel-v1.json" \
  --markdown-output "$LOOP_TMP/evidence-gated-loop-kernel-v1.md"
```

Expected stdout:

```json
{"record_status":"valid","status":"built"}
```

Before replacing generated artifacts, prove that only the registry/non-claim projection changes:

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python - "$LOOP_TMP" <<'PY'
import json
from pathlib import Path
import sys

root = Path.cwd()
tmp = Path(sys.argv[1])
old = json.loads(
    (root / "docs/evidence/evidence-gated-loop-kernel-v1.json")
    .read_text(encoding="utf-8")
)
new = json.loads(
    (tmp / "evidence-gated-loop-kernel-v1.json").read_text(encoding="utf-8")
)

for key in ("cases", "verification_results", "summary", "limits"):
    assert new[key] == old[key], key
assert new["kernel_id"] == old["kernel_id"]
assert new["kernel_version"] == old["kernel_version"]
assert new["schema_version"] == old["schema_version"]
assert new["registry"]["value"]["case_paths"] == old["registry"]["value"]["case_paths"]
assert (
    new["registry"]["value"]["verification_profiles"]
    == old["registry"]["value"]["verification_profiles"]
)
assert new["non_claims"] != old["non_claims"]
assert new["registry"]["value"]["non_claims"] != (
    old["registry"]["value"]["non_claims"]
)
PY
```

Use the generated files as bulk deterministic outputs to replace the two canonical report files. Remove only `LOOP_TMP` after the replacement and comparison complete.

- [ ] **Step 6: Run focused GREEN and canonical gate**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_v0_1_6_release_metadata.py \
  tests/unit/test_evidence_gated_loop_contracts.py \
  tests/unit/test_evidence_gated_loop_profiles.py \
  tests/integration/test_evidence_gated_loop_gate.py \
  tests/unit/test_public_truth_documentation.py \
  tests/unit/test_documentation_contracts.py

PYTHON_DOTENV_DISABLED=1 .venv/bin/python \
  scripts/evidence_gated_loop_gate.py check
```

Expected gate stdout:

```json
{"match":true,"record_status":"valid","status":"valid"}
```

- [ ] **Step 7: Prove protected surfaces remain exact**

Run:

```bash
test "$(sha256sum benchmarks/evidence-gated-loop-v1/cases/context-resolver-projection.json | cut -d' ' -f1)" = \
  "9d51fb053848e52a1e76499fe0002cc6dfb7d02f2485d937ae5773e9447abbfc"
test "$(sha256sum benchmarks/evidence-gated-loop-v1/cases/evaluation-sensitivity.json | cut -d' ' -f1)" = \
  "f728d745eff37a8e83d7b5fd0f8430dfd93579cc10d47ea609d96966cc5fc4af"
test "$(sha256sum benchmarks/evidence-gated-loop-v1/cases/strict-citation-consumer.json | cut -d' ' -f1)" = \
  "55a2b855f4e3128ef94fb370530b4816882118e29feba065ff48f3def57a8eea"
test "$(sha256sum constraints.txt | cut -d' ' -f1)" = \
  "d8ddec45f8d50210458651e453d68beafa916c6358d1d47a71ac8f72db75295f"
test "$(sha256sum .github/workflows/ci.yml | cut -d' ' -f1)" = \
  "8eefc4b077d8c24eaf5cf3328790b675b204a38476700e2065b6c6df3ae6ee0e"
git diff --exit-code HEAD~1 -- scripts/evidence_gated_loop_profiles.py \
  VERSION frontend/package.json frontend/package-lock.json
```

Expected: exit `0`.

- [ ] **Step 8: Commit Phase A public and canonical truth**

```bash
git add \
  scripts/evidence_gated_loop_contracts.py \
  benchmarks/evidence-gated-loop-v1/registry.json \
  docs/evidence/evidence-gated-loop-kernel-v1.json \
  docs/evidence/evidence-gated-loop-kernel-v1.md \
  README.md README_CN.md CHANGELOG.md \
  docs/reference/evidence-gated-loop-kernel.md \
  docs/superpowers/README.md \
  tests/unit/test_public_truth_documentation.py \
  tests/unit/test_documentation_contracts.py
git commit -m "fix(loop): bind immutable v0.1.6 release record"
```

---

### Task 3: Close Phase A and Stop for Independent Review

**Files:**
- Verify only; no file change is expected.

**Interfaces:**
- Consumes: the two Phase A semantic commits and the approved spec/plan.
- Produces: one clean exact Phase A candidate suitable for authority review and a separately authorized PR.

- [ ] **Step 1: Verify the pinned environment**

Run:

```bash
test -x .venv/bin/python || {
  echo DRA_PINNED_ENVIRONMENT_REQUIRED
  exit 1
}

test "$(.venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" = "3.11"
.venv/bin/python - <<'PY'
import pydantic, pytest, pytest_asyncio
assert pydantic.__version__ == "2.13.4"
assert pytest.__version__ == "9.0.3"
assert pytest_asyncio.__version__ == "1.4.0"
PY
```

Run the repository's exact normalized-constraints comparison. `uv pip check` may return only the already reviewed diagnostic:

```text
The package ragflow-sdk requires pytest>=8.0.0,<9.0.0, but 9.0.3 is installed
```

Any second incompatibility or any import/test failure blocks Phase A.

- [ ] **Step 2: Run the complete provider-free retained command matrix**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python scripts/agent_evaluation_gate.py check
PYTHON_DOTENV_DISABLED=1 .venv/bin/python scripts/agent_evaluation_v2_gate.py check
PYTHON_DOTENV_DISABLED=1 .venv/bin/python scripts/evidence_gated_loop_gate.py check
PYTHON_DOTENV_DISABLED=1 .venv/bin/python scripts/run_creation_idempotency_proof.py check
PYTHON_DOTENV_DISABLED=1 .venv/bin/python scripts/run_dispatch_reconciliation_proof.py check
PYTHON_DOTENV_DISABLED=1 .venv/bin/python scripts/run_failure_cause_proof.py check
PYTHON_DOTENV_DISABLED=1 .venv/bin/python scripts/secure_local_runtime_proof.py check
PYTHON_DOTENV_DISABLED=1 .venv/bin/python scripts/bounded_live_producer_proof.py check
PYTHON_DOTENV_DISABLED=1 .venv/bin/python scripts/downstream_consumer_contract.py check \
  --input docs/evidence/downstream-consumer-contract-v1.json
PYTHON_DOTENV_DISABLED=1 .venv/bin/python scripts/run_execution_recovery_proof.py check
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q -m "not docker"
.venv/bin/python scripts/check_canonical_identity.py --root .
.venv/bin/python scripts/final_presentation_audit.py --root .
```

Expected: every command exits `0`; the Loop gate prints the exact valid JSON line.

- [ ] **Step 3: Run frontend and required Docker verification**

Before Docker, record:

```bash
docker system df
docker ps -a --format '{{.ID}} {{.Names}} {{.Status}}'
docker volume ls --format '{{.Name}}'
docker network ls --format '{{.ID}} {{.Name}}'
docker image ls --format '{{.Repository}}:{{.Tag}} {{.ID}}'
```

Run the Docker lane only with the task's unique Compose ownership and its documented cleanup:

```bash
DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS=true \
PYTHON_DOTENV_DISABLED=1 \
  .venv/bin/python -m pytest -q -m docker
```

Then:

```bash
(
  cd frontend
  npm ci
  npm run test
  npm run lint
  npm run build
  npm audit --audit-level=moderate
)
```

Expected: all commands pass, and the post-Docker inventory contains no task-owned residue.

- [ ] **Step 4: Audit exact Phase A scope and private boundaries**

Run:

```bash
git diff --check "$PHASE_A_IMPLEMENTATION_BASE"...HEAD
git status --short
git diff --name-status "$PHASE_A_IMPLEMENTATION_BASE"...HEAD
```

The implementation-only diff must contain exactly:

```text
CHANGELOG.md
README.md
README_CN.md
benchmarks/evidence-gated-loop-v1/registry.json
docs/evidence/evidence-gated-loop-kernel-v1.json
docs/evidence/evidence-gated-loop-kernel-v1.md
docs/reference/evidence-gated-loop-kernel.md
docs/superpowers/README.md
scripts/evidence_gated_loop_contracts.py
tests/unit/test_documentation_contracts.py
tests/unit/test_public_truth_documentation.py
tests/unit/test_v0_1_6_release_metadata.py
```

Run an exact set check:

```bash
.venv/bin/python - "$PHASE_A_IMPLEMENTATION_BASE" <<'PY'
import subprocess
import sys

base = sys.argv[1]
actual = set(
    subprocess.check_output(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        text=True,
    ).splitlines()
)
expected = {
    "CHANGELOG.md",
    "README.md",
    "README_CN.md",
    "benchmarks/evidence-gated-loop-v1/registry.json",
    "docs/evidence/evidence-gated-loop-kernel-v1.json",
    "docs/evidence/evidence-gated-loop-kernel-v1.md",
    "docs/reference/evidence-gated-loop-kernel.md",
    "docs/superpowers/README.md",
    "scripts/evidence_gated_loop_contracts.py",
    "tests/unit/test_documentation_contracts.py",
    "tests/unit/test_public_truth_documentation.py",
    "tests/unit/test_v0_1_6_release_metadata.py",
}
assert actual == expected, (sorted(actual - expected), sorted(expected - actual))
PY
```

Also run:

```bash
git diff --check 8064a33bec6dfb403149e056a373f074c2cea409...HEAD
git diff --name-status 8064a33bec6dfb403149e056a373f074c2cea409...HEAD
```

The complete PR diff must contain the twelve implementation paths above plus
exactly the approved release spec and implementation plan. Scan tracked
additions for actual home paths, coordination UUIDs, credential assignments,
XML entities, provider payloads, and consumer-repository edits. Generic
rejection literals in safety tests are not private leakage.

Run the same exact set check from original `main`, adding only:

```text
docs/superpowers/specs/2026-07-29-v0-1-7-evidence-governed-reliability-release-design.md
docs/superpowers/plans/2026-07-29-v0-1-7-evidence-governed-reliability-release-implementation-plan.md
```

- [ ] **Step 5: Stop at the Phase A authority gate**

Return:

```text
READY_FOR_PHASE_A_AUTHORITY_REVIEW
```

Include exact HEAD/tree, base, commits, changed paths, RED/GREEN evidence, focused/full/Docker/frontend results, generated artifact hashes, known metadata diagnostic, final clean status, and non-actions.

Do not push or create a PR until separately authorized. Phase B must not begin until Phase A is reviewed, merged, and exact merge-SHA hosted CI/CodeQL succeeds.

---

## External Gate A: Phase A Publication and Merge

After authority review and explicit authorization:

1. Push the exact reviewed Phase A HEAD without force.
2. Create a Ready PR with a Simplified Chinese title/body.
3. Read back persisted title, body, base, head, draft state, and exact head OID.
4. Require the exact current hosted set on the reviewed head:
   `Backend Tests`, `Secure Local Runtime Containers`,
   `Frontend Demo Console`, `Analyze (actions)`,
   `Analyze (javascript-typescript)`, and `Analyze (python)`. Every one must be
   `completed/success`; a missing, added-required, pending, skipped, cancelled,
   timed-out, or failed check blocks.
5. Re-read comments, reviews, inline comments, review threads, and changed files.
6. Merge only after separate explicit merge authorization and exact-head match.
7. Verify squash merge tree equals the reviewed tree.
8. Verify the same exact six hosted checks on the squash merge SHA.
9. Keep Release disposition `hold`; do not tag or publish.

Persist the exact squash merge SHA and tree as
`EXPECTED_PHASE_A_MERGE_COMMIT` and `EXPECTED_PHASE_A_MERGE_TREE`; verify the
merge tree equals the reviewed Phase A tree. Only that exact merged Phase A
`main` may become the Phase B base.

---

### Task 4: Define and Implement the v0.1.7 Release Identity

**Files:**
- Create: `tests/unit/test_v0_1_7_release_metadata.py`
- Modify: `tests/unit/test_release_metadata.py`
- Modify: `tests/unit/test_documentation_contracts.py`
- Create: `docs/releases/v0.1.7.md`
- Modify: `VERSION`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`

**Interfaces:**
- Consumes: merged Phase A `main`, immutable historical release-note hashes, and existing release-note structure.
- Produces: current release identity `0.1.7`, release preparation date `2026-07-29`, and `V017_RELEASE_NOTES`.

- [ ] **Step 1: Start Phase B only from merged Phase A main**

Authority creates a new project worktree task and branch:

```text
codex/v0-1-7-release-preparation
```

The new task must verify:

```bash
git fetch --prune origin
git status --short
test "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)"
test -n "${EXPECTED_PHASE_A_MERGE_COMMIT:-}" || {
  echo DRA_PHASE_A_MERGE_IDENTITY_REQUIRED
  exit 1
}
test "$(git rev-parse HEAD)" = "$EXPECTED_PHASE_A_MERGE_COMMIT" || {
  echo DRA_PHASE_B_BASE_MISMATCH
  exit 1
}
test -n "${EXPECTED_PHASE_A_MERGE_TREE:-}" || {
  echo DRA_PHASE_A_MERGE_TREE_IDENTITY_REQUIRED
  exit 1
}
test "$(git rev-parse HEAD^{tree})" = "$EXPECTED_PHASE_A_MERGE_TREE" || {
  echo DRA_PHASE_B_BASE_TREE_MISMATCH
  exit 1
}
test "$(
  gh api repos/iTao-AI/decision-research-agent/git/ref/heads/main \
    --jq .object.sha
)" = "$EXPECTED_PHASE_A_MERGE_COMMIT" || {
  echo DRA_PHASE_B_REMOTE_BASE_MISMATCH
  exit 1
}
git log -1 --oneline
gh pr list --state open --json number,title,headRefOid
```

`EXPECTED_PHASE_A_MERGE_COMMIT` is supplied by the authority from External
Gate A's persisted squash-merge readback, together with
`EXPECTED_PHASE_A_MERGE_TREE`; neither identity is inferred from a mutable
branch. Expected: clean exact merged Phase A `main` and no conflicting open
release PR. Record this exact commit as `PHASE_B_BASE`. If another commit has
landed on `main`, stop for a new authority compatibility review rather than
silently absorbing it.

Before creating any dated release artifact, run:

```bash
test "$(TZ=Asia/Shanghai date +%F)" = "2026-07-29" || {
  echo DRA_V017_RELEASE_DATE_REVIEW_REQUIRED
  exit 1
}
```

Expected: exit `0`. If the date has changed, stop. Authority must approve one
replacement release-preparation date, and the release note, changelog, and
their tests must be updated together. Do not silently preserve or normalize
the old date.

Verify the new task-local pinned environment before any RED edit:

```bash
test -x .venv/bin/python || {
  echo DRA_PINNED_ENVIRONMENT_REQUIRED
  exit 1
}
test "$(.venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" = "3.11"
.venv/bin/python - <<'PY'
import pydantic, pytest, pytest_asyncio
assert pydantic.__version__ == "2.13.4"
assert pytest.__version__ == "9.0.3"
assert pytest_asyncio.__version__ == "1.4.0"
PY
```

Run the same normalized 96-pin comparison and diagnostic-only metadata check
as Phase A. A missing environment requires separate authority to create/install
it; a second incompatibility or an import failure blocks implementation.

- [ ] **Step 2: Add RED current-version and release-note tests**

Create `tests/unit/test_v0_1_7_release_metadata.py` with:

```python
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RELEASE_DATE = "2026-07-29"
V017_RELEASE_NOTES = PROJECT_ROOT / "docs" / "releases" / "v0.1.7.md"
V017_H2_ORDER = (
    "Supported Surface",
    "Changes",
    "Compatibility And Migration",
    "Rollback",
    "Required Verification",
    "Known Limits",
)
HISTORICAL_RELEASE_NOTE_SHA256 = {
    "v0.1.0.md": "96088198dae7236c05f5bdc5b37f69f126f76c4e4191c7affd36a41d247b8ef2",
    "v0.1.1.md": "2debd84d4383a6335e54ff59cad3521c458698c4ca2b3eb78b4303a8933bbbf7",
    "v0.1.2.md": "4fbde856a85bd5be4ec0d38640f50119024b9dd980b86479b9d7af658789f5bb",
    "v0.1.3.md": "f1b4f34fce15463994645a7e4be0fee03cb22428541116afd96ba45e47c5431d",
    "v0.1.4.md": "2dd2b7650ce0d8f57e8f63954f49165fb1b0974cbc597cf14a414675b3aa8bba",
    "v0.1.5.md": "61cbac951a6513a3eb8f160647b9f16b95ca6ed96a4cca8bea80786462a90b6b",
    "v0.1.6.md": "0cb73ea51e8aae8d4e997a0225a31439dbc11b2977692d3510b8d33d1963552e",
}
REQUIRED_VERIFICATION_COMMANDS = (
    "python scripts/agent_evaluation_gate.py check",
    "python scripts/agent_evaluation_v2_gate.py check",
    "python scripts/evidence_gated_loop_gate.py check",
    "python scripts/run_creation_idempotency_proof.py check",
    "python scripts/run_dispatch_reconciliation_proof.py check",
    "python scripts/run_failure_cause_proof.py check",
    "python scripts/secure_local_runtime_proof.py check",
    "python scripts/bounded_live_producer_proof.py check",
    "python scripts/downstream_consumer_contract.py check",
    "python scripts/run_execution_recovery_proof.py check",
    'python -m pytest -q -m "not docker"',
    "python -m pytest -q -m docker",
    "python scripts/check_canonical_identity.py --root .",
    "python scripts/final_presentation_audit.py --root .",
    "npm ci",
    "npm run test",
    "npm run lint",
    "npm run build",
    "npm audit --audit-level=moderate",
)
PREMATURE_CLAIM_PATTERNS = (
    r"\bv0\.1\.7 is published\b",
    r"\bv0\.1\.7 tag (?:has been |was )?(?:created|published)\b",
    r"\bgithub release (?:has been |was )?published\b",
    r"\barchive smoke (?:has |was )?(?:passed|completed)\b",
    r"\bdeployment (?:has been |was )?completed\b",
    r"\blive-provider strict success (?:has been |was )?"
    r"(?:achieved|completed|demonstrated|proved)\b",
    r"\b(?:achieved|completed|demonstrated|proved) "
    r"live-provider strict success\b",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _collapsed(text: str) -> str:
    return " ".join(text.split())


def _sections(notes: str) -> dict[str, str]:
    matches = list(re.finditer(r"^## (.+)$", notes, re.MULTILINE))
    assert tuple(match.group(1) for match in matches) == V017_H2_ORDER
    return {
        match.group(1): notes[
            match.end():
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(notes)
        ]
        for index, match in enumerate(matches)
    }


def test_v0_1_7_version_identity_is_consistent() -> None:
    package = json.loads(_read(PROJECT_ROOT / "frontend/package.json"))
    lock = json.loads(_read(PROJECT_ROOT / "frontend/package-lock.json"))
    assert _read(PROJECT_ROOT / "VERSION").strip() == "0.1.7"
    assert package["version"] == "0.1.7"
    assert lock["version"] == "0.1.7"
    assert lock["packages"][""]["version"] == "0.1.7"
    assert V017_RELEASE_NOTES.exists()


def test_v0_1_7_release_notes_have_closed_sections() -> None:
    notes = _read(V017_RELEASE_NOTES)
    sections = {key: _collapsed(value) for key, value in _sections(notes).items()}
    assert notes.startswith(
        "# Decision Research Agent v0.1.7\n\n"
        f"Release preparation date: {RELEASE_DATE}."
    )
    supported = sections["Supported Surface"]
    for phrase in (
        "Online execution emits privacy-safe evidence",
        "provider-free offline evaluation",
        "humans own release and rollback decisions",
        "startup convergence protects application state after crashes",
        "Application database state remains business authority",
        "LangGraph checkpoints remain execution-position state",
        "Observation and optional tracing remain diagnostic",
        "does not mutate runtime state or authorize its own release",
        "Context Reliability Regression v1",
        "privacy-safe observation",
        "Agent Evaluation Sensitivity Gate v2",
        "generic-strict-citation@1",
        "Evidence-Gated Loop Kernel v1",
        "Crash-Safe Startup Convergence v1",
    ):
        assert phrase in supported
    for phrase in (
        "Context Reliability Regression v1",
        "privacy-safe observation",
        "Agent Evaluation Sensitivity Gate v2",
        "generic-strict-citation@1",
        "Evidence-Gated Loop Kernel v1",
        "Crash-Safe Startup Convergence v1",
    ):
        assert phrase in sections["Changes"]
    for phrase in (
        "dra.downstream-consumer.v1",
        "commit-based producer tuple",
        "Raw observation",
        "010_run_execution_recovery",
        "stopped writers",
        "ragflow-sdk 0.13.0",
        "pytest==9.0.3",
    ):
        assert phrase in sections["Compatibility And Migration"]
    for phrase in (
        "bfd744a5611c7673d9385a45bed0131d6cb47655",
        "complete pre-010 backup",
        "does not prove an unrestricted downgrade",
    ):
        assert phrase in sections["Rollback"]
    for command in REQUIRED_VERIFICATION_COMMANDS:
        assert command in sections["Required Verification"]
        for heading, body in sections.items():
            if heading != "Required Verification":
                assert command not in body
    for phrase in (
        "No autonomous evolution",
        "No live-provider strict success",
        "exact resume",
        "multi-instance high availability",
        "SLA",
        "external-user adoption",
        "business impact",
        "No source truth",
        "Existing independent consumer proof does not prove acceptance",
        "observed transport artifact",
    ):
        assert phrase in sections["Known Limits"]
    lowered = notes.lower()
    for pattern in PREMATURE_CLAIM_PATTERNS:
        assert re.search(pattern, lowered) is None


def test_v0_1_7_preserves_historical_release_notes() -> None:
    for filename, expected in HISTORICAL_RELEASE_NOTE_SHA256.items():
        path = PROJECT_ROOT / "docs" / "releases" / filename
        assert sha256(path.read_bytes()).hexdigest() == expected
```

In `tests/unit/test_release_metadata.py`:

- add `V017_RELEASE_NOTES`;
- change only current-version assertions from `0.1.6` to `0.1.7`;
- retain every `v0.1.6` historical test and phrase;
- leave current SECURITY, README, docs discovery, and changelog-placement
  assertions unchanged until Task 5 changes them atomically with their
  documents.

In `tests/unit/test_documentation_contracts.py`, remove only the unrelated
root `VERSION == "0.1.6"` assertion from
`test_dispatch_public_truth_documents_the_owned_recovery_boundary`. Current
release identity is already owned by `tests/unit/test_release_metadata.py` and
the new versioned release contract; a dispatch/recovery documentation test
must not permanently couple itself to one mutable release version. Its
dispatch/recovery evidence assertions remain unchanged.

- [ ] **Step 3: Run release tests and confirm RED**

Run:

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_v0_1_7_release_metadata.py \
  tests/unit/test_release_metadata.py::test_current_release_version_is_consistent
```

Expected: failures because `v0.1.7.md` is absent and current root versions
still say `0.1.6`. Separately run the dispatch documentation-contract test
after removing its unrelated version assertion; it must remain green before
and after the version bump. Do not create RED assertions for SECURITY or
discovery in this task; those files intentionally remain coherent at `v0.1.6`
until Task 5.

- [ ] **Step 4: Create the exact v0.1.7 release note**

Create `docs/releases/v0.1.7.md` with this structure and content:

````markdown
# Decision Research Agent v0.1.7

Release preparation date: 2026-07-29.

## Supported Surface

Online execution emits privacy-safe evidence; provider-free offline evaluation
detects bounded failure modes and retains consumer-derived verification; humans
own release and rollback decisions; startup convergence protects application
state after crashes.

v0.1.7 packages the reviewed post-v0.1.6 surface as Context Reliability
Regression v1, privacy-safe observation, Agent Evaluation Sensitivity Gate v2,
the opt-in `generic-strict-citation@1` profile, Evidence-Gated Loop Kernel v1,
and Crash-Safe Startup Convergence v1. Required verification remains
provider-free. Publication, deployment, and provider-backed execution remain
separate actions.

Application database state remains business authority. LangGraph checkpoints
remain execution-position state. Observation and optional tracing remain
diagnostic. Offline verification records reviewed evidence and decisions but
does not mutate runtime state or authorize its own release.

## Changes

### Context Reliability Regression v1

- Added retained context-projection regressions for production-coherent
  resolver and persisted terminal-state pairs.
- Unknown and incompatible combinations fail closed without changing runtime
  business authority.

### Privacy-safe observation

- Project-owned WebSocket, `stream_writer`, console, and retained telemetry/API
  observations use closed descriptors, stable codes, bounded projection, and
  fixed messages.
- Canonical tool inputs, persisted results/artifacts, and terminal results
  remain the supported content authorities.

### Agent Evaluation Sensitivity Gate v2

- Added provider-free one-dimensional controls proving that each responsible
  evaluator detects its declared failure dimension while unrelated projections
  remain stable.
- This is evaluator-sensitivity evidence, not a model-quality or production
  result.

### Strict exact-source citation

- Added opt-in `generic-strict-citation@1`, fail-closed finalization, bounded
  correction, exact public-HTTPS admission, and preserved literal-generic
  compatibility.
- Independent provider-free consumer contract evidence remains pinned to its
  exact commit-based producer tuple; this release does not reinterpret that
  evidence as tag-based consumer acceptance.

### Evidence-Gated Loop Kernel v1

- Added fixed provider-free retained and safety profiles over three reviewed
  failure and verification lineages.
- Online execution remains evidence-only. Human review owns diagnosis, carrier,
  verdict, release, and rollback recommendation.
- Historical episode `release_disposition=hold` values remain unchanged; this
  release is a later separate human-reviewed repository decision.
- The [canonical provider-free Loop evidence](../evidence/evidence-gated-loop-kernel-v1.md)
  remains the inspectable retained record.

### Crash-Safe Startup Convergence v1

- Added one process-lifetime DB-scoped writer gate, startup-only convergence of
  abandoned application-owned running state, private boot/owner fencing, and
  authenticated idempotent one-hop replacement.
- Added provider-free real-process SIGKILL, migration, replay, stale-writer,
  and exact old-revision rollback proof.

### Release-lineage and maintenance

- Corrected the fixed v0.1.6 selector to verify the immutable historical
  release record without requiring the mutable repository root to stay at
  version 0.1.6.
- Included the already-merged GitHub Actions and frontend dependency
  maintenance. Python dependency pins remain unchanged.

## Compatibility And Migration

`dra.downstream-consumer.v1` and literal `generic` behavior remain compatible.
`generic-strict-citation@1` remains opt-in. Existing independent consumer proof
remains bound to its exact commit-based producer tuple; publication of this tag
does not silently replace that identity or prove tag-based consumer acceptance.

Raw observation `args`, `result`, and `error` semantics changed in place to
privacy-safe descriptors and stable codes. Consumers needing substantive
content must use canonical tool inputs, persisted results/artifacts, or terminal
result authority.

Migration `010_run_execution_recovery` requires stopped writers, creation and
preservation of its dedicated pre-010 backup, and exactly one active application
writer during startup. Do not edit owner rows or migration markers manually.
Explicit replacement creates a new run, not resume, and may repeat provider or
tool effects.

Python pins remain unchanged. `ragflow-sdk 0.13.0` still declares
`pytest>=8.0.0,<9.0.0` while the deliberate no-deps release lock uses
`pytest==9.0.3`. The full real suite is release authority; this known metadata
diagnostic is not represented as a conflict-free dependency graph. Any
additional incompatibility blocks release.

## Rollback

Stop all writers before changing application revisions.

If migration 010 has not been applied, restore a previously approved source and
dependency pin together.

If migration 010 has been applied, preserve the post-010 database, obtain
explicit approval for post-backup data loss, restore the complete pre-010
backup, and verify it from exact old revision
`bfd744a5611c7673d9385a45bed0131d6cb47655` in an isolated archived source
root before accepting writes.

The existing proof validates that exact pre-recovery revision. It does not
prove an unrestricted downgrade of a migrated database directly to the v0.1.6
tag. Consumer rollback remains a separate decision to retain or restore an
already approved immutable producer pin.

## Required Verification

Release preparation requires fresh provider-free evidence from the exact
release candidate:

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_gate.py check
PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_v2_gate.py check
PYTHON_DOTENV_DISABLED=1 python scripts/evidence_gated_loop_gate.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_creation_idempotency_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_dispatch_reconciliation_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_failure_cause_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/secure_local_runtime_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/bounded_live_producer_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/downstream_consumer_contract.py check \
  --input docs/evidence/downstream-consumer-contract-v1.json
PYTHON_DOTENV_DISABLED=1 python scripts/run_execution_recovery_proof.py check
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m "not docker"
DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS=true \
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m docker
python scripts/check_canonical_identity.py --root .
python scripts/final_presentation_audit.py --root .

cd frontend
npm ci
npm run test
npm run lint
npm run build
npm audit --audit-level=moderate
```

These commands do not run a provider, model, tool, search, `observe-live`, or
remote LangSmith tracing. Deterministic proofs, required Docker verification,
local exact-commit archive smoke, and post-publication source-archive
observation remain separate evidence boundaries.

## Known Limits

- This tracked preparation document does not itself prove that an annotated
  v0.1.7 tag, GitHub Release, source-archive observation, deployment, or live
  provider execution has completed.
- No autonomous evolution, runtime self-modification, automatic diagnosis,
  candidate generation, release, or rollback is provided.
- No live-provider strict success, exact resume, exactly-once external effects,
  multi-instance high availability, hosted production, deployment, or SLA is
  claimed.
- No source truth, universal research quality, universal Agent quality,
  external-user adoption, or business impact is claimed.
- Existing independent consumer proof does not prove acceptance of the v0.1.7
  tag.
- A GitHub-generated archive checksum is an observed transport artifact; the
  repository, annotated tag, peeled commit, and tree are the immutable producer
  identity.
````

- [ ] **Step 5: Bump only release root identity**

Set:

```text
VERSION = 0.1.7
frontend/package.json version = 0.1.7
frontend/package-lock.json version = 0.1.7
frontend/package-lock.json packages[""].version = 0.1.7
```

Do not change dependency entries or lock resolution.

- [ ] **Step 6: Run focused GREEN**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_v0_1_7_release_metadata.py \
  tests/unit/test_release_metadata.py \
  tests/unit/test_documentation_contracts.py
```

Expected: all tests in both files pass. This is a coherent intermediate commit:
root release identity and the new release-note contract are `v0.1.7`, while
unchanged SECURITY/README/docs discovery still consistently describe the last
published/current public surface as `v0.1.6` until Task 5.

- [ ] **Step 7: Commit release identity and notes**

```bash
git add VERSION frontend/package.json frontend/package-lock.json \
  docs/releases/v0.1.7.md tests/unit/test_release_metadata.py \
  tests/unit/test_v0_1_7_release_metadata.py \
  tests/unit/test_documentation_contracts.py
git commit -m "docs(release): prepare v0.1.7 identity"
```

---

### Task 5: Publish Coherent v0.1.7 Current Truth

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `README.md`
- Modify: `README_CN.md`
- Modify: `SECURITY.md`
- Modify: `docs/README.md`
- Modify: `docs/operations/run-execution-recovery.md`
- Modify: `docs/reference/observation-contract.md`
- Modify: `docs/reference/evidence-gated-loop-kernel.md`
- Modify: `tests/unit/test_public_truth_documentation.py`
- Modify: `tests/unit/test_documentation_contracts.py`
- Modify: `tests/unit/test_v0_1_7_release_metadata.py`
- Modify: `tests/unit/test_release_metadata.py`

**Interfaces:**
- Consumes: `docs/releases/v0.1.7.md` and the already-merged capability docs.
- Produces: one current release discovery path and explicit historical `hold`, observation migration, recovery rollback, and consumer-pin boundaries.

- [ ] **Step 1: Replace unreleased-truth tests with release-preparation truth**

Change the current public-truth tests so they:

```python
def test_v0_1_7_public_truth_is_current_and_bounded() -> None:
    changelog = _read("CHANGELOG.md")
    released = _section(
        changelog,
        "## [0.1.7] - 2026-07-29",
        "## [0.1.6] - 2026-07-24",
    )
    normalized = " ".join(released.split())
    for phrase in (
        "Context Reliability Regression",
        "Privacy-safe observation contract",
        "Agent evaluation sensitivity evidence",
        "Strict exact-source citation profile",
        "Evidence-Gated Loop Kernel",
        "Crash-safe startup convergence",
        "Immutable v0.1.6 release-lineage selector",
    ):
        assert phrase in released
    assert released.count("### Immutable v0.1.6 release-lineage selector") == 1
    unreleased = _section(
        changelog,
        "## [Unreleased]",
        "## [0.1.7] - 2026-07-29",
    )
    assert "### Immutable v0.1.6 release-lineage selector" not in unreleased
    assert "release_disposition=hold" in normalized
    assert "separate human-reviewed repository release decision" in normalized
    assert "not runtime self-modification" in normalized


def test_v0_1_7_current_docs_do_not_claim_tag_publication() -> None:
    corpus = "\n".join(
        _read(path)
        for path in (
            "README.md",
            "README_CN.md",
            "SECURITY.md",
            "docs/README.md",
            "docs/releases/v0.1.7.md",
        )
    ).lower()
    for pattern in (
        r"\bv0\.1\.7 is published\b",
        r"\bv0\.1\.7 tag (?:has been |was )?(?:created|published)\b",
        r"\bgithub release (?:has been |was )?published\b",
        r"\barchive smoke (?:has |was )?(?:passed|completed)\b",
        r"\bdeployment (?:has been |was )?completed\b",
        r"\blive-provider strict success (?:has been |was )?"
        r"(?:achieved|completed|demonstrated|proved)\b",
        r"\b(?:achieved|completed|demonstrated|proved) "
        r"live-provider strict success\b",
    ):
        assert re.search(pattern, corpus) is None
```

In `tests/unit/test_release_metadata.py`, change the mutable-current
SECURITY/README/docs-index/changelog assertions from `v0.1.6` to `v0.1.7` in
the same edit as those documents. Retain the immutable `v0.1.6` note hashes,
release-note section contract, and historical discovery link. Require exactly
one `current supported surface` entry, assigned to `v0.1.7`, with `v0.1.6`
explicitly historical. Replace the old mutable `Decision Research Agent
v0.1.6 ships` security assertion with `Decision Research Agent v0.1.7 release
preparation includes`, and reject `Decision Research Agent v0.1.7 ships`
before the public tag/Release gate.

Update the recovery documentation contract to require:

```text
v0.1.7 release preparation includes this recovery surface
historical release `hold`
does not itself prove publication
```

and to reject the obsolete literal:

```text
No published v0.1.7.
```

Update the English/Chinese verification-inventory contract to require the
Loop and crash-recovery commands in both README files, with value-equal command
sets. Retain the existing selected-subset versus complete-release-matrix
boundary.

- [ ] **Step 2: Run the new current-truth tests and confirm RED**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_release_metadata.py \
  tests/unit/test_public_truth_documentation.py \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_v0_1_7_release_metadata.py
```

Expected: assertions fail because the changelog and current documents still describe the surface as unreleased.

- [ ] **Step 3: Freeze the v0.1.7 changelog section**

Leave `## [Unreleased]` present and empty apart from future additions. Create:

```markdown
## [0.1.7] - 2026-07-29
```

Move the existing complete post-`v0.1.6` entries beneath it without weakening their technical non-claims. Add:

```markdown
### Context Reliability Regression

- Added retained provider-free regressions that reject unknown and
  production-incoherent resolver/persisted terminal-state combinations while
  preserving application-owned state authority.
```

Move the existing Phase A `### Immutable v0.1.6 release-lineage selector`
subsection and its two bullets from `[Unreleased]` into `[0.1.7]` byte-for-byte.
Do not add a second copy. The final changelog must contain exactly one such
subsection, and `[Unreleased]` must not contain it.

In the Loop section, preserve:

```text
release_disposition=hold
```

and state:

```text
The historical hold remains unchanged; v0.1.7 is a later separate
human-reviewed repository release decision, not a kernel action.
```

- [ ] **Step 4: Update the English and Chinese README current truth**

The English Loop section must contain:

```text
The v0.1.6 selector verifies only the immutable v0.1.6 release record; it
does not execute historical release behavior. The immutable v0.1.6 release
does not contain this kernel. The v0.1.7 release preparation includes it
through a later separate human review; canonical episode hold decisions remain
historical evidence.
```

The Chinese Loop section must contain:

```text
v0.1.6 selector 只验证不可变的 v0.1.6 release record，不执行历史 release
行为。不可变的 v0.1.6 release 不包含该 kernel；v0.1.7 release
preparation 通过后续独立人工审查纳入它，canonical episode 的 hold 决策仍是历史证据。
```

The English recovery section must begin:

```text
The v0.1.7 release preparation includes a process-lifetime DB-scoped exclusive
writer gate, startup-only convergence for application-owned running state, and
an explicit authenticated one-hop replacement.
```

Its final paragraph must state:

```text
The implementation phase retained release hold. v0.1.7 is a later separate
human-reviewed repository release decision; this README does not itself prove
tag or GitHub Release publication.
```

Write the equivalent bounded Chinese text. Add `v0.1.7` as the current release-notes link and retain `v0.1.6` as historical.

In both README verification sections, keep the English and Chinese command
inventories value-equal and add these already-required CI proofs:

```text
Evidence-Gated Loop Kernel: python scripts/evidence_gated_loop_gate.py check
Crash-safe execution recovery proof: python scripts/run_execution_recovery_proof.py check
```

Also include both commands in the selected local verification subset. Preserve
the existing explanation that this subset is not the complete release matrix.
The Loop reference's `Prerequisites And First Result` remains the shortest
operator path: its fixed check must produce
`{"match":true,"record_status":"valid","status":"valid"}` without provider
credentials.

- [ ] **Step 5: Update SECURITY, docs discovery, observation, Loop reference, and recovery runbook**

The opening `SECURITY.md` paragraph must start with
`Decision Research Agent v0.1.7 release preparation includes` rather than a
claim that the tag or GitHub Release already ships, and must include:

- context reliability;
- privacy-safe observation;
- strict citation;
- evidence-gated offline verification;
- crash-safe single-node recovery;
- required verification remains provider-free;
- hosted/multi-tenant/multi-replica operation remains out of scope.

`docs/README.md` must contain exactly one `current supported surface`, assigned to `v0.1.7`; `v0.1.6` becomes historical.

In `docs/reference/observation-contract.md`, replace `under [Unreleased]` with:

```text
first included in the v0.1.7 release preparation
```

and preserve the fact that it was not included in immutable `v0.1.6`.

In `docs/reference/evidence-gated-loop-kernel.md`, preserve the Phase A immutable-selector sentence and add:

```text
Canonical episode release dispositions remain historical reviewed outcomes.
The v0.1.7 repository release is a later separate human decision and does not
rewrite or execute those outcomes.
```

In `docs/operations/run-execution-recovery.md`, replace the opening with:

```markdown
This runbook covers the single-node SQLite crash-safety boundary introduced by
migration `010_run_execution_recovery`. It provides startup-only convergence,
not runtime monitoring. The implementation phase retained historical release
`hold`; v0.1.7 release preparation includes this recovery surface through a
later separate human review. This runbook does not itself prove publication.
```

Replace `No published v0.1.7.` with:

```text
- No automatic release or rollback.
```

Do not alter the stopped-writer upgrade, backup, `bfd744a...` verifier, or data-loss rollback instructions.

- [ ] **Step 6: Run focused GREEN**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_release_metadata.py \
  tests/unit/test_v0_1_6_release_metadata.py \
  tests/unit/test_v0_1_7_release_metadata.py \
  tests/unit/test_public_truth_documentation.py \
  tests/unit/test_documentation_contracts.py
```

Expected: all tests pass.

- [ ] **Step 7: Prove historical release notes are unchanged**

```bash
sha256sum docs/releases/v0.1.{0,1,2,3,4,5,6}.md
```

Expected exact hashes are the seven values in `HISTORICAL_RELEASE_NOTE_SHA256`.

- [ ] **Step 8: Commit v0.1.7 current truth**

```bash
git add CHANGELOG.md README.md README_CN.md SECURITY.md docs/README.md \
  docs/operations/run-execution-recovery.md \
  docs/reference/observation-contract.md \
  docs/reference/evidence-gated-loop-kernel.md \
  tests/unit/test_release_metadata.py \
  tests/unit/test_public_truth_documentation.py \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_v0_1_7_release_metadata.py
git commit -m "docs(release): align v0.1.7 public truth"
```

---

### Task 6: Freeze the Phase B Release Candidate

**Files:**
- Verify only; no file change is expected.

**Interfaces:**
- Consumes: Phase B release identity and current-truth commits.
- Produces: one exact clean `v0.1.7` release candidate ready for authority review.

- [ ] **Step 1: Run focused release, Loop, recovery, and presentation suites**

```bash
PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m pytest -q \
  tests/unit/test_release_metadata.py \
  tests/unit/test_v0_1_6_release_metadata.py \
  tests/unit/test_v0_1_7_release_metadata.py \
  tests/unit/test_evidence_gated_loop_contracts.py \
  tests/unit/test_evidence_gated_loop_profiles.py \
  tests/integration/test_evidence_gated_loop_gate.py \
  tests/unit/test_run_execution_migrations.py \
  tests/unit/test_run_recovery_lifecycle.py \
  tests/unit/test_run_recovery_repository.py \
  tests/integration/test_run_execution_recovery_proof.py \
  tests/unit/test_public_truth_documentation.py \
  tests/unit/test_documentation_contracts.py
```

Expected: all tests pass.

- [ ] **Step 2: Run the complete provider-free command matrix**

Run the exact ten proof/check commands, full non-Docker suite, canonical identity, and presentation audit from Task 3.

Expected: every command exits `0`. The Loop gate must remain green after root version becomes `0.1.7`; this is the retained proof for the original release-selector failure.

- [ ] **Step 3: Run required Docker and frontend verification**

Repeat the Docker inventory, unique task-owned Docker lane, exact cleanup, and frontend commands from Task 3.

Expected: all commands pass; no task-owned Docker residue remains.

- [ ] **Step 4: Run a local exact-commit source archive smoke**

This is provider-free and happens before tag creation:

```bash
RELEASE_CANDIDATE="$(git rev-parse HEAD)"
RELEASE_TREE="$(git rev-parse HEAD^{tree})"
ARCHIVE_TASK_ROOT="$(mktemp -d)"
ARCHIVE_FILE="$ARCHIVE_TASK_ROOT/release-candidate.tar"
ARCHIVE_ROOT="$ARCHIVE_TASK_ROOT/source"
PINNED_PYTHON="$(pwd)/.venv/bin/python"

git archive --format=tar --output="$ARCHIVE_FILE" "$RELEASE_CANDIDATE"
LOCAL_ARCHIVE_SHA256="$(sha256sum "$ARCHIVE_FILE" | cut -d' ' -f1)"
mkdir "$ARCHIVE_ROOT"
tar -xf "$ARCHIVE_FILE" -C "$ARCHIVE_ROOT"
test "$(cat "$ARCHIVE_ROOT/VERSION")" = "0.1.7"

(
  cd "$ARCHIVE_ROOT"
  PYTHON_DOTENV_DISABLED=1 "$PINNED_PYTHON" -m pytest -q \
    tests/unit/test_release_metadata.py \
    tests/unit/test_v0_1_6_release_metadata.py \
    tests/unit/test_v0_1_7_release_metadata.py \
    tests/unit/test_public_truth_documentation.py \
    tests/unit/test_documentation_contracts.py
  "$PINNED_PYTHON" scripts/check_canonical_identity.py --root .
  "$PINNED_PYTHON" scripts/final_presentation_audit.py --root .
)

"$PINNED_PYTHON" - "$ARCHIVE_TASK_ROOT" <<'PY'
from pathlib import Path
import shutil
import sys
import tempfile

target = Path(sys.argv[1]).resolve()
temp_root = Path(tempfile.gettempdir()).resolve()
if target == temp_root or temp_root not in target.parents:
    raise SystemExit(f"refusing unsafe archive cleanup: {target}")
shutil.rmtree(target)
PY
```

Before removal, record the exact commit, tree, `LOCAL_ARCHIVE_SHA256`,
release-note SHA-256, and version/package/lock root identities. This smoke does
not run the recovery old-revision proof because a source archive has no Git
history.

- [ ] **Step 5: Audit the exact Phase B allowlist**

Run:

```bash
git diff --check "$PHASE_B_BASE"...HEAD
git diff --name-status "$PHASE_B_BASE"...HEAD
git status --short
```

Allowed Phase B paths are exactly:

```text
CHANGELOG.md
README.md
README_CN.md
SECURITY.md
VERSION
docs/README.md
docs/operations/run-execution-recovery.md
docs/reference/evidence-gated-loop-kernel.md
docs/reference/observation-contract.md
docs/releases/v0.1.7.md
frontend/package-lock.json
frontend/package.json
tests/unit/test_documentation_contracts.py
tests/unit/test_public_truth_documentation.py
tests/unit/test_release_metadata.py
tests/unit/test_v0_1_7_release_metadata.py
```

No dependency entry, runtime, API, migration, canonical evidence, historical release note, consumer fixture, workflow, or consumer repository may change.

Run an exact set check:

```bash
.venv/bin/python - "$PHASE_B_BASE" <<'PY'
import subprocess
import sys

base = sys.argv[1]
actual = set(
    subprocess.check_output(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        text=True,
    ).splitlines()
)
expected = {
    "CHANGELOG.md",
    "README.md",
    "README_CN.md",
    "SECURITY.md",
    "VERSION",
    "docs/README.md",
    "docs/operations/run-execution-recovery.md",
    "docs/reference/evidence-gated-loop-kernel.md",
    "docs/reference/observation-contract.md",
    "docs/releases/v0.1.7.md",
    "frontend/package-lock.json",
    "frontend/package.json",
    "tests/unit/test_documentation_contracts.py",
    "tests/unit/test_public_truth_documentation.py",
    "tests/unit/test_release_metadata.py",
    "tests/unit/test_v0_1_7_release_metadata.py",
}
assert actual == expected, (sorted(actual - expected), sorted(expected - actual))
PY
```

- [ ] **Step 6: Stop at the Phase B authority gate**

Return:

```text
READY_FOR_PHASE_B_AUTHORITY_REVIEW
```

Include exact HEAD/tree/base, commits, changed-file allowlist, RED/GREEN evidence, full/Docker/frontend/archive results, hashes, known metadata diagnostic, clean status, and non-actions.

Do not push, create a PR, merge, tag, or publish.

---

## External Gate B: Phase B Publication and Merge

After authority review and explicit authorization:

1. Push the exact reviewed Phase B HEAD without force.
2. Create a Ready PR with a Simplified Chinese title/body.
3. Read back persisted PR identity and exact head OID.
4. Require the same exact six current hosted checks named in External Gate A
   to be `completed/success` on that head.
5. Re-read comments, reviews, threads, and changed files.
6. Merge only after separate exact-head merge authorization.
7. Verify squash merge tree equals the reviewed tree.
8. Verify remote `main` equals the squash merge commit.
9. Require the same exact six checks to be `completed/success` on the merge
   SHA.
10. Do not tag or publish until the separate Release gate below.

Persist the exact Phase B squash merge SHA and tree as
`EXPECTED_RELEASE_COMMIT` and `EXPECTED_RELEASE_TREE`. Verify that the merge
tree equals the reviewed Phase B tree. Task 7 must stop if `main` advances
before publication; it may not silently publish a later commit.

---

### Task 7: Create and Publish the Immutable v0.1.7 Release

**Files:**
- No tracked file change.

**Interfaces:**
- Consumes: exact Phase B squash merge commit/tree, merge-SHA hosted success, and explicit tag/Release authorization.
- Produces: annotated tag `v0.1.7`, public non-draft/non-prerelease GitHub Release, and persisted exact identity readback.

- [ ] **Step 1: Fresh-check publication preconditions**

```bash
git fetch --prune origin
test -z "$(git status --short)"
test "$(gh repo view --json nameWithOwner --jq .nameWithOwner)" = \
  "iTao-AI/decision-research-agent"
test -n "${EXPECTED_RELEASE_COMMIT:-}" || {
  echo DRA_V017_RELEASE_COMMIT_IDENTITY_REQUIRED
  exit 1
}
test -n "${EXPECTED_RELEASE_TREE:-}" || {
  echo DRA_V017_RELEASE_TREE_IDENTITY_REQUIRED
  exit 1
}
RELEASE_COMMIT="$EXPECTED_RELEASE_COMMIT"
RELEASE_TREE="$EXPECTED_RELEASE_TREE"
test "$(git rev-parse origin/main)" = "$RELEASE_COMMIT" || {
  echo DRA_V017_RELEASE_MAIN_DRIFT
  exit 1
}
test "$(git rev-parse origin/main^{tree})" = "$RELEASE_TREE" || {
  echo DRA_V017_RELEASE_TREE_DRIFT
  exit 1
}
test "$(gh api repos/iTao-AI/decision-research-agent/git/ref/heads/main --jq .object.sha)" = \
  "$RELEASE_COMMIT"
test "$(git rev-parse HEAD^{tree})" = "$RELEASE_TREE"
gh pr list --state open \
  --json number,title,headRefName,headRefOid,baseRefName
```

Reject only an open PR whose title or head names `v0.1.7` release preparation,
or whose changed scope conflicts with this exact release. Unrelated
Dependabot/maintenance PRs do not change the immutable `RELEASE_COMMIT` and are
not a publication blocker.

Probe the tag-ref and Release endpoints with `gh api --include`, writing stdout
and stderr to task-owned temporary files. Treat the resource as absent only
when the first returned HTTP status line is an explicit `404`. Authentication,
authorization, rate-limit, DNS, TLS, timeout, empty-response, or any other
transport failure is `DRA_V017_PUBLICATION_PROBE_FAILED`, never absence.
Do not use `if gh release view ...` or an empty `git ls-remote` substitution as
an existence oracle.

Use:

```bash
PUBLICATION_PROBE_ROOT="$(mktemp -d)"
probe_github_resource() {
  probe_name="$1"
  endpoint="$2"
  output="$PUBLICATION_PROBE_ROOT/$probe_name.out"
  error="$PUBLICATION_PROBE_ROOT/$probe_name.err"
  if gh api --include "$endpoint" >"$output" 2>"$error"; then
    printf '%s\n' present
    return 0
  fi
  first_line="$(sed -n '1p' "$output")"
  case "$first_line" in
    HTTP/*" 404 "*) printf '%s\n' absent ;;
    *)
      printf '%s\n' DRA_V017_PUBLICATION_PROBE_FAILED >&2
      return 2
      ;;
  esac
}

TAG_STATE="$(
  probe_github_resource tag \
    repos/iTao-AI/decision-research-agent/git/ref/tags/v0.1.7
)" || exit $?
RELEASE_STATE="$(
  probe_github_resource release \
    repos/iTao-AI/decision-research-agent/releases/tags/v0.1.7
)" || exit $?
```

Classify the persisted state:

| Remote tag | GitHub Release | Allowed action |
|---|---|---|
| absent | absent | create the annotated tag, push once, then create Release |
| exact annotated tag | absent | resume by verifying/fetching the exact tag, then create Release |
| exact annotated tag | exact Release | readback-only closeout; create nothing |
| absent | present | invalid; hard stop |
| mismatch or probe error | any | hard stop |

An exact existing tag must have `object.type == "tag"`; its tag object must
name `v0.1.7`, peel to `RELEASE_COMMIT`, and therefore to `RELEASE_TREE`.
An existing local tag must also be annotated and peel to the same commit/tree.
If the remote exact tag exists and the local tag is absent, fetch only that
exact ref into the absent local ref:

```bash
git fetch origin refs/tags/v0.1.7:refs/tags/v0.1.7
```

Then verify object, peeled commit, and tree equality before continuing; do not
recreate it. Any local/remote mismatch blocks. This state machine is the only
resume lane after partial publication.

Re-read merge-SHA hosted checks. Any non-success or identity mismatch blocks publication.
The observed latest check name set must equal the six names fixed in External
Gate A, and every latest run must be `completed/success`. Record the check-run
IDs and URLs against `RELEASE_COMMIT`; do not accept a successful run from a
different SHA or infer success from workflow configuration.

- [ ] **Step 2: Re-run the local exact-commit archive smoke**

Repeat Task 6 Step 4 against `RELEASE_COMMIT`, not a mutable local branch. Record the same identities and require the release note body to equal the tracked file.

- [ ] **Step 3: Obtain explicit tag and GitHub Release authorization**

Stop until the user authorizes:

```text
annotated v0.1.7 tag + non-draft non-prerelease GitHub Release
```

This approval does not authorize deployment, asset upload, tag rewrite, tag deletion, or Release deletion.

- [ ] **Step 4: Create and push the annotated tag once**

When both local and remote tags are absent:

```bash
git tag -a v0.1.7 "$RELEASE_COMMIT" \
  -m "Decision Research Agent v0.1.7"
test "$(git rev-parse 'v0.1.7^{commit}')" = "$RELEASE_COMMIT"
test "$(git rev-parse 'v0.1.7^{tree}')" = "$RELEASE_TREE"
git push origin refs/tags/v0.1.7
```

When an exact local tag exists and the remote tag is absent, push that existing
object once without recreating it. When the exact remote tag already exists,
skip tag creation/push and continue from readback. No force option is
permitted.

If the push returns nonzero, inspect the exact remote tag ref before any retry.
If the remote ref exists, treat the push as having had a public side effect and
continue only from persisted readback. If it does not exist, retain the local
task-created tag and return `BLOCKED`; do not delete, recreate, or retry it
without a new authority decision.

- [ ] **Step 5: Publish the tracked release note**

For every state, including readback-only recovery from an exact existing
Release, first materialize the body from the immutable release commit, not a
mutable working file:

```bash
RELEASE_NOTES_FILE="$(mktemp)"
git show "$RELEASE_COMMIT:docs/releases/v0.1.7.md" >"$RELEASE_NOTES_FILE"
cmp -s docs/releases/v0.1.7.md "$RELEASE_NOTES_FILE"

```

Run `gh release create` only when the Release probe returned explicit `404`.
If an exact Release already exists, skip creation and perform readback only.
Do not upload custom assets and do not deploy.

For the explicit-`404` state, run:

```bash
gh release create v0.1.7 \
  --repo iTao-AI/decision-research-agent \
  --title "Decision Research Agent v0.1.7" \
  --notes-file "$RELEASE_NOTES_FILE" \
  --verify-tag
```

If `gh release create` returns nonzero, read back
`releases/tags/v0.1.7` with the same explicit-status probe before deciding
whether the Release was created. An exact persisted Release is authoritative
even if the client reported failure. An explicit `404` retains the public
annotated tag and returns `BLOCKED`; a transport/probe error returns
`DRA_V017_PUBLICATION_PROBE_FAILED`. Never delete or move the tag.

- [ ] **Step 6: Read back persisted public identity**

```bash
LOCAL_TAG_OBJECT="$(git rev-parse v0.1.7)"
LOCAL_PEELED="$(git rev-parse 'v0.1.7^{commit}')"
LOCAL_TREE="$(git rev-parse 'v0.1.7^{tree}')"
REMOTE_TAG_OBJECT="$(
  gh api repos/iTao-AI/decision-research-agent/git/ref/tags/v0.1.7 \
    --jq .object.sha
)"

test "$LOCAL_PEELED" = "$RELEASE_COMMIT"
test "$LOCAL_TREE" = "$RELEASE_TREE"
test "$REMOTE_TAG_OBJECT" = "$LOCAL_TAG_OBJECT"

RELEASE_READBACK_JSON="$(mktemp)"
RELEASE_READBACK_BODY="$(mktemp)"
test -n "${RELEASE_NOTES_FILE:-}"
gh api repos/iTao-AI/decision-research-agent/releases/tags/v0.1.7 \
  >"$RELEASE_READBACK_JSON"
"$(pwd)/.venv/bin/python" - "$RELEASE_READBACK_JSON" \
  "$RELEASE_READBACK_BODY" <<'PY'
import json
from pathlib import Path
import sys

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(
    {
        "tag_name": payload.get("tag_name"),
        "target_commitish": payload.get("target_commitish"),
        "draft": payload.get("draft"),
        "prerelease": payload.get("prerelease"),
        "name": payload.get("name"),
        "assets_length": len(payload.get("assets", [])),
    }
)
body = payload.get("body")
assert isinstance(body, str)
Path(sys.argv[2]).write_text(body, encoding="utf-8")
PY
cmp -s "$RELEASE_NOTES_FILE" "$RELEASE_READBACK_BODY"
```

Require:

- `tag_name == "v0.1.7"`;
- `target_commitish` resolves to `RELEASE_COMMIT`;
- `draft == false`;
- `prerelease == false`;
- `name == "Decision Research Agent v0.1.7"`;
- body equals `docs/releases/v0.1.7.md`;
- no custom assets.

Resolve `target_commitish` against the fetched repository and require the
resulting commit/tree to equal `RELEASE_COMMIT`/`RELEASE_TREE`; do not accept
the field as an uninterpreted string.

Parsing the API JSON is mandatory: `gh api --jq .body > file` appends its own
output newline and cannot be used as a byte-equality oracle for a tracked note
that already ends in newline. Remove only `RELEASE_READBACK_JSON` and
`RELEASE_READBACK_BODY`, `RELEASE_NOTES_FILE`, and the tag/Release probe
temporary files after every equality and identity check passes. Any mismatch
blocks closeout and must not be repaired by editing the tracked note or
rewriting the tag.

---

### Task 8: Observe the Published Source Archive and Close the Phase

**Files:**
- No tracked file change.

**Interfaces:**
- Consumes: public `v0.1.7` tag/Release and pinned local environment.
- Produces: bounded post-publication transport observation and clean release closeout.

- [ ] **Step 1: Download the public source archive into a task-owned directory**

```bash
ARCHIVE_TASK_ROOT="$(mktemp -d)"
ARCHIVE_FILE="$ARCHIVE_TASK_ROOT/v0.1.7.tar.gz"
PINNED_PYTHON="$(pwd)/.venv/bin/python"
curl --fail --location --silent --show-error \
  --output "$ARCHIVE_FILE" \
  https://github.com/iTao-AI/decision-research-agent/archive/refs/tags/v0.1.7.tar.gz
ARCHIVE_SHA256="$(sha256sum "$ARCHIVE_FILE" | cut -d' ' -f1)"

ARCHIVE_EXTRACT_ROOT="$ARCHIVE_TASK_ROOT/extracted"
"$PINNED_PYTHON" - "$ARCHIVE_FILE" "$ARCHIVE_EXTRACT_ROOT" <<'PY'
from pathlib import Path, PurePosixPath
import stat
import sys
import tarfile

archive_path = Path(sys.argv[1])
destination = Path(sys.argv[2])
prefix = PurePosixPath("decision-research-agent-0.1.7")
archive_bytes_max = 128 * 1024 * 1024
member_bytes_max = 64 * 1024 * 1024
total_bytes_max = 256 * 1024 * 1024
members_max = 20_000

observed = archive_path.lstat()
assert stat.S_ISREG(observed.st_mode)
assert 0 < observed.st_size <= archive_bytes_max
assert not destination.exists()

with tarfile.open(archive_path, mode="r:gz") as source:
    members = source.getmembers()
    assert 0 < len(members) <= members_max
    seen: set[str] = set()
    total_bytes = 0
    for member in members:
        path = PurePosixPath(member.name)
        assert member.name
        assert "\x00" not in member.name and "\\" not in member.name
        assert not path.is_absolute()
        assert all(part not in {"", ".", ".."} for part in path.parts)
        assert path.parts[0] == str(prefix)
        folded = member.name.casefold().rstrip("/")
        assert folded not in seen
        seen.add(folded)
        assert not any(
            key.lower().startswith("gnu.sparse")
            for key in member.pax_headers
        )
        assert member.isdir() or member.isreg()
        if member.isreg():
            assert 0 <= member.size <= member_bytes_max
            total_bytes += member.size
            assert total_bytes <= total_bytes_max

    destination.mkdir()
    resolved_destination = destination.resolve()
    for member in members:
        path = PurePosixPath(member.name)
        target = destination.joinpath(*path.parts)
        parent = target.parent.resolve()
        assert (
            parent == resolved_destination
            or resolved_destination in parent.parents
        )
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        stream = source.extractfile(member)
        assert stream is not None
        with target.open("xb") as output:
            remaining = member.size
            while remaining:
                chunk = stream.read(min(64 * 1024, remaining))
                assert chunk
                output.write(chunk)
                remaining -= len(chunk)
            assert stream.read(1) == b""
        target.chmod(member.mode & 0o755)
PY

ARCHIVE_ROOT="$ARCHIVE_EXTRACT_ROOT/decision-research-agent-0.1.7"
test -d "$ARCHIVE_ROOT"
```

The observed archive checksum is recorded as transport evidence only; it does
not replace tag/commit/tree identity. The task-owned downloaded archive is
untrusted input until the bounded extractor has rejected absolute/traversal
names, symlinks/hardlinks/devices, duplicate case-folded paths, sparse entries,
oversized members, and an unexpected top-level prefix.

- [ ] **Step 2: Run bounded provider-free archive checks**

```bash
test "$(cat "$ARCHIVE_ROOT/VERSION")" = "0.1.7"

(
  cd "$ARCHIVE_ROOT"
  PYTHON_DOTENV_DISABLED=1 "$PINNED_PYTHON" -m pytest -q \
    tests/unit/test_release_metadata.py \
    tests/unit/test_v0_1_6_release_metadata.py \
    tests/unit/test_v0_1_7_release_metadata.py \
    tests/unit/test_public_truth_documentation.py \
    tests/unit/test_documentation_contracts.py
  "$PINNED_PYTHON" scripts/check_canonical_identity.py --root .
  "$PINNED_PYTHON" scripts/final_presentation_audit.py --root .
)
```

Do not run the recovery old-revision proof from the GitHub archive because it intentionally lacks Git history.

- [ ] **Step 3: Remove only task-owned archive resources**

```bash
"$PINNED_PYTHON" - "$ARCHIVE_TASK_ROOT" <<'PY'
from pathlib import Path
import shutil
import sys
import tempfile

target = Path(sys.argv[1]).resolve()
temp_root = Path(tempfile.gettempdir()).resolve()
if target == temp_root or temp_root not in target.parents:
    raise SystemExit(f"refusing unsafe archive cleanup: {target}")
shutil.rmtree(target)
PY
```

Confirm the explicit path is beneath the task-created temporary root before removal. Do not remove shared caches, environments, repositories, tags, or Docker resources.

- [ ] **Step 4: Final public and local readback**

Verify:

```bash
gh release view v0.1.7 \
  --repo iTao-AI/decision-research-agent \
  --json tagName,targetCommitish,isDraft,isPrerelease,name,publishedAt,url
git status --short
git worktree list --porcelain
git branch --all --format='%(refname:short)'
```

Confirm remote `main`, tag peeled commit, tag tree, Release target, and release body remain coherent.

- [ ] **Step 5: Return final closeout**

Return:

```text
RELEASED_READY_FOR_CLEANUP
```

Include exact tag object, peeled commit, tree, GitHub Release URL, merge-SHA checks, archive observation SHA, provider-free results, residual diagnostic, non-claims, and exact task-owned worktree/branch cleanup identity.

Local branch/worktree deletion and ignored-environment cleanup remain separately authorized.

---

## Plan Self-Review Checklist

- Spec coverage: Phase A owns the mutable-current selector defect; Phase B owns version/public truth; publication and archive observation remain separate human gates.
- Candidate/verifier isolation: Phase A is merged before Phase B starts. The `v0.1.7` candidate does not modify the verifier that accepts it.
- Historical integrity: all case files, episodes, verdicts, consumer proof, release dispositions, v0.1.6 notes, and earlier release notes remain immutable.
- Runtime boundary: no Agent, API, database, migration, dependency-pin, downstream-fixture, provider, or consumer-repository change is planned.
- Release semantics: historical `hold` remains historical; publication is a later human decision.
- Consumer identity: commit-pinned independent proof is not reinterpreted as tag acceptance.
- Migration boundary: stopped-writer backup/restore and exact `bfd744a...` verification remain the only proven post-010 rollback path.
- Evidence separation: deterministic proofs, required Docker, local exact-commit archive smoke, GitHub archive observation, hosted checks, and public Release state have distinct authority.
- Failure policy: any new dependency incompatibility, current proof failure, hosted failure, identity mismatch, or out-of-allowlist path blocks.
- Publication safety: no force push, tag movement, silent tag deletion, custom asset, deployment, or release claim before persisted readback.
- Plan contains no deferred implementation marker, unresolved substitution token, or instruction to infer missing code.
- Type consistency: `_assert_v0_1_6_historical_identity`, `V017_RELEASE_NOTES`, `PHASE_B_BASE`, release tag, commit, tree, and archive identities have one meaning throughout.

---

## AutoPlan Phase 1 — CEO Review

Mode: `SELECTIVE EXPANSION`. UI scope is absent, so Design Review is skipped.
Developer/release-operator scope is present, so Engineering and DevEx reviews
remain required.

### Premise Challenge

| Premise | Review | Decision |
|---|---|---|
| The next valuable action is a release rather than another Agent feature | Supported by merged reliability/evaluation/recovery evidence and the absence of a higher-value live gap | Keep the release-only direction |
| `v0.1.7` can be one implementation PR | False because the release candidate would otherwise modify the fixed verifier that judges it | Keep Phase A and Phase B as separate reviewed/merged PRs |
| Historical Loop `hold` blocks later publication | False; the ADR assigns release authority to later human review | Preserve historical `hold`; record publication as a separate decision |
| The `v0.1.6` selector can be corrected without a profile bump | Conditionally true only as narrow compatible maintenance: listed profile contract fields and intended invariant remain unchanged, the exact repository commit identifies the implementation, and the repair lands before the candidate | Add an explicit compatibility boundary and stop condition |
| Existing consumer proof can be relabeled as tag acceptance | False; it remains pinned to its exact commit-based producer tuple | Keep the consumer repository and proof identity unchanged |
| A fixed preparation date can be carried forward silently | False | Add `DRA_V017_RELEASE_DATE_REVIEW_REQUIRED` |

The user already approved the release premise and two-PR structure. This review
found no reason to challenge that product direction.

### What Already Exists

| Sub-problem | Existing authority reused |
|---|---|
| Release identity | `VERSION`, frontend package roots, `tests/unit/test_release_metadata.py` |
| Historical release integrity | `docs/releases/v0.1.0.md` through `v0.1.6.md`, changelog section hashes |
| Fixed offline verification | `scripts/evidence_gated_loop_profiles.py`, registry, canonical JSON/Markdown reports |
| Consumer-derived evidence | immutable strict-citation case and commit-pinned independent consumer proof |
| Recovery proof and rollback | migration `010`, recovery proof, exact old-revision verifier, operator runbook |
| Public safety | `final_presentation_audit.py`, `check_canonical_identity.py`, documentation contracts |
| Publication evidence | exact-head CI/CodeQL, annotated tag/peeled commit/tree readback, GitHub Release readback |

No new manifest, SBOM system, signing service, hosted observability, evaluator
platform, runtime role, or provider attempt is required.

### Dream State Delta

```text
CURRENT
  merged post-v0.1.6 evidence on mutable main
    |
    v
THIS PLAN
  historical verifier bridge
    -> coherent v0.1.7 source candidate
    -> exact-head CI and human release decision
    -> immutable tag/commit/tree plus bounded archive observation
    |
    v
12-MONTH IDEAL
  repeatable evidence-governed release cadence
    -> each material capability has retained proof
    -> release/rollback decisions remain human-owned
    -> consumers choose and verify immutable pins independently
```

The plan closes the current release gap. It deliberately does not build the
12-month release platform in advance.

### Implementation Alternatives

| Approach | Effort | Risk | Benefit | Decision |
|---|---:|---:|---|---|
| No change; leave evidence on `main` | Low | High truth/discovery drift | Avoids publication work | Rejected |
| One PR for verifier and release | Medium | High self-verification ambiguity | Faster merge count | Rejected |
| Two PRs plus separate publication gates | Medium | Low and auditable | Clean verifier/candidate separation and rollback | Selected |
| Add a new generalized release manifest/signing/EvalOps system | High | High scope expansion | Possible future automation | Deferred; no live need |

### Temporal Interrogation

| Time | Likely failure | Plan response |
|---|---|---|
| Hour 1 | historical selector still owns mutable current truth | Phase A refactors it to immutable historical authority |
| Hours 2-4 | canonical report changes beyond the single non-claim | temporary build plus structural equality checks |
| Hours 4-6 | release identity is updated before current docs | Task 4 keeps an independently green intermediate contract; Task 5 changes current docs/tests atomically |
| After first PR | candidate begins from an unmerged verifier branch | External Gate A requires exact merged `main` |
| Publication day | date, head, tag, tree, or Release target drifts | Asia/Shanghai preparation-date review and exact identity readbacks |
| Post-publication | archive transport is mistaken for producer authority | tag/commit/tree remain primary; archive hash is observation only |

### Review Sections 1–10

1. **Architecture:** The two-PR graph is sound after adding the narrow verifier
   compatibility classification. No runtime/data-plane component is added.
2. **Error and rescue:** Every external mutation has a preflight and stop; tag
   movement, identity drift, new dependency conflict, or failed proof cannot be
   repaired by weakening tests.
3. **Security and threat model:** The plan adds no provider, credential, auth,
   network-service, or deployment surface. Existing Docker execution remains
   task-owned and bounded.
4. **Data flow and interaction edges:** The important flows are current release
   truth, immutable historical truth, canonical Loop regeneration, migration
   rollback, and publication identity. They are separated in the task graph.
5. **Code quality:** Reuse the existing release-test helpers and fixed gate.
   Do not create another release framework or duplicate current/historical
   ownership across version-specific files.
6. **Tests:** The original plan omitted parts of Supported Surface, Required
   Verification, Known Limits, and premature-publication coverage. These are
   now explicit in the `v0.1.7` release-note contract.
7. **Performance:** No runtime hot path changes. Full-suite, Docker, frontend,
   and archive gates are intentionally serial release costs.
8. **Observability and debuggability:** Existing stable proof outputs, test
   failures, exact Git identities, and persisted GitHub state are sufficient.
   No hosted tracing is introduced.
9. **Deployment and rollout:** This is a source release, not a deployment.
   Merge, tag, Release, and archive observation are separate human gates.
10. **Long-term trajectory:** The release creates a strong evidence-governed
    reliability narrative without claiming autonomous evolution. Future work
    should start from new consumer or failure evidence, not a standing feature
    queue.

### Error and Rescue Registry

| Failure | Stable stop/result | Rescue owner | Prohibited rescue |
|---|---|---|---|
| Wrong Phase B base | `PHASE_B_BASE` mismatch | authority creates a fresh candidate from merged Phase A | merge/cherry-pick around the gate |
| Preparation date drift | `DRA_V017_RELEASE_DATE_REVIEW_REQUIRED` | authority chooses one new date | silently keep the old date |
| Historical release-byte drift | focused hash test RED | restore exact historical bytes | update the expected hash |
| Canonical Loop drift beyond non-claim | structural comparison failure | isolate the first unexpected field | accept regenerated baselines |
| New dependency incompatibility | release blocked | separate dependency decision | normalize pins in release work |
| Hosted check failure | publication blocked | evidence-derived targeted repair | retry until green without diagnosis |
| Tag/commit/tree/Release mismatch | publication/closeout blocked | stop and reconcile exact identities | move or force-push a published tag |
| Archive observation failure | release remains published but not closed | retain evidence and decide patch/deprecation separately | rewrite history |

### Failure Modes Registry

| Failure mode | Severity | Prevention/evidence | Status |
|---|---:|---|---|
| Candidate modifies its own verifier | Critical | Phase A merges before Phase B | Closed by architecture |
| Compatible maintenance becomes an unversioned semantic expansion | Critical | closed compatibility criteria plus stop condition | Closed in spec/plan |
| Version bump and public truth form a known-RED commit | High | Task 4/5 ownership split and full intermediate release tests | Closed in plan |
| Duplicate changelog selector subsection | High | move the Phase A subsection and assert count `1` | Closed in plan |
| Release note under-specifies supported surface/non-claims | High | section-scoped contract and negative patterns | Closed in plan |
| Release date becomes false | Medium | hard Asia/Shanghai date gate | Closed in plan |
| Public plan leaks local restore metadata | High | remove restore comment before freeze and run presentation audit | Pending finalization gate |

### CEO Dual Voices

The independent strategy voice supported the release-only direction and found
contract/coherence gaps in the mutable `v0.1.6` selector, intermediate test
ownership, changelog movement, release-note coverage, date handling, and causal
storytelling. The Codex CLI voice did not complete a final report and is marked
`[codex-unavailable]`; its one repo-verifiable finding about verifier
compatibility/version boundaries was independently checked against the ADR and
reference and incorporated narrowly.

| Dimension | Independent voice | Codex CLI | Consensus |
|---|---|---|---|
| Premises valid | Yes | N/A | Not dual-confirmed |
| Right problem | Release is highest-value current problem | N/A | Not dual-confirmed |
| Scope calibration | Two PRs; no new platform | Compatibility boundary flagged | Compatible |
| Alternatives explored | No-change/one-PR/new-platform compared | N/A | Not dual-confirmed |
| Market risk | Main-only evidence weakens demonstration | N/A | Not dual-confirmed |
| Six-month trajectory | Publish bounded proof, then evidence-triggered work | N/A | Not dual-confirmed |

There is no user challenge and no taste decision. The approved direction stands.

### CEO NOT in Scope

- runtime self-modification or automatic permanent rules;
- generalized EvalOps, release orchestration, manifest, signing, or SBOM work;
- another provider attempt or tag-based consumer re-pin;
- deployment, hosted service, multi-instance HA, SLA, or business-impact claim;
- new Agent roles, dynamic tool discovery, context compaction, or framework
  migration.

### CEO Completion Summary

| Area | Result |
|---|---|
| Product direction | Clean: release-only remains highest-value |
| Premises | One compatibility premise narrowed; date premise gated |
| Existing leverage | Existing tests/proofs/docs/GitHub gates reused |
| Scope | Two PRs plus separate publication actions |
| Critical gaps found | 2: verifier compatibility ambiguity; known-RED intermediate ownership |
| High gaps found | 4: mutable historical selector, changelog duplication, release-note coverage, private restore marker |
| Deferred expansions | release platform/signing/SBOM/hosted EvalOps |
| User challenge | None |
| Unresolved CEO decisions | 0 after the spec compatibility clarification lands |

### Book-Aligned CEO Self-Review

The plan follows the book's separation: online execution records bounded
evidence; offline evaluation aggregates and verifies reviewed trajectories;
candidate acceptance, publication, and rollback remain explicit human
decisions. Harness, Evaluation, Observability, and continuous evolution are
represented as governed evidence paths, not runtime self-rewrite. The release
does not claim “Graph Engineering” or multi-agent value without new information
flow.

---

## AutoPlan Phase 3 — Engineering Review

Result: `PASS AFTER AMENDMENTS`. No implementation may begin from the
pre-amendment plan snapshot.

### Architecture and Dependency Graph

```text
immutable v0.1.6 release note + changelog section
                    |
                    v
Phase A historical selector
  -> unchanged strict profile argv/case/episode semantics
  -> regenerated presentation-only Loop projections
  -> reviewed Phase A tree
                    |
                    v
exact Phase A squash merge SHA/tree + six hosted checks
                    |
                    v
Phase B release identity + release note
  -> coherent current public truth
  -> full provider-free/Docker/frontend/archive verification
  -> reviewed Phase B tree
                    |
                    v
exact Phase B squash merge SHA/tree + six hosted checks
                    |
                    v
human tag/Release authorization
  -> annotated tag -> peeled commit -> tree
  -> exact commit-sourced Release body
  -> safe bounded public-archive observation
```

The dependency graph is intentionally serial. Phase B cannot consume a feature
branch, stale `origin/main`, or an unreviewed main advance. Publication cannot
consume a mutable checkout body or an unrelated successful check run.

### Engineering Findings and Resolutions

| Severity | Finding | Verified live evidence | Resolution in this plan |
|---|---|---|---|
| P0 | strict-consumer case hash was mistyped | live SHA-256 contains `...70530b...` | both protected-hash gates use the exact live value |
| P0 | positive-claim regex rejected its required `No live-provider strict success` non-claim | same phrase was both required and forbidden | negative checks now target only affirmative achieved/completed/demonstrated/proved claims |
| P0 | Task 4 version bump left an unrelated dispatch documentation test fixed at `0.1.6` | live documentation contract contains the hidden assertion | remove the cross-domain version coupling in Task 4 and run the whole documentation-contract file |
| P0 | `gh api --jq .body` adds an output newline | live v0.1.6 readback is one byte longer than the tracked note | parse complete API JSON and compare exact body bytes |
| P0 | public plan contained restore metadata rejected by the presentation audit | live audit forbids restore/local markers | remove the restore comment before plan freeze and rerun public scans |
| P1 | Phase B base was only `HEAD == origin/main` | stale or later main could satisfy the old gate | lock authority-provided Phase A merge SHA/tree and compare HEAD, origin, and GitHub main |
| P1 | release-note example used nested equal-length fences | inner bash fence closed the outer Markdown example | use a four-backtick outer fence |
| P1 | local archive smoke promised a hash without creating an archive file | old command streamed directly into extraction | create and hash a task-owned tar before extraction |
| P1 | publication existence probes conflated 404 with transport/auth failure | old `if`/empty-output checks were fail-open | explicit HTTP-status probes and a closed absent/exact/mismatch/error state machine |
| P1 | partial tag success had no safe resume lane | a later preflight rejected every existing tag | allow exact-tag/no-Release resume; never recreate, move, or delete a tag |
| P1 | Release body was sourced from the current checkout | clean status alone does not bind it to the merge tree | materialize the note from `RELEASE_COMMIT` and compare all later readbacks to those bytes |
| P1 | downloaded source archive used direct extraction | external transport artifact was trusted before validation | bounded regular-file/directory-only extractor with path, type, prefix, count, and size gates |
| P2 | 96-pin statement had no executable command | plan referenced an unstated comparison | one shared deterministic metadata gate now checks all 96 normalized pins |
| P2 | all open PRs were treated as release blockers | unrelated maintenance PRs do not alter the release commit | block only conflicting release work; immutable main/tree/check identities remain authority |

### Test Strategy

```text
Task 1 RED
  missing historical-only helper
    -> GREEN complete v0.1.6 historical file

Task 2 RED
  old mutable selector wording / missing bounded maintenance contract
    -> GREEN Loop contracts + regenerated structural equality + canonical gate

Phase A retained matrix
  10 provider-free proofs/checks
  + full non-Docker
  + Docker lane
  + frontend
  + presentation/identity
  + exact 12-path implementation allowlist

Task 4 RED
  absent v0.1.7 note and old root identity
    -> GREEN complete release files + complete documentation contracts

Task 5 RED
  unreleased/current-doc mismatch
    -> GREEN release/current/history/non-claim contracts

Phase B retained matrix
  Phase A selector retained on root 0.1.7
  + all proof/check lanes
  + local exact-commit archive
  + exact 16-path allowlist

Publication
  exact hosted checks
  + closed tag/Release state machine
  + commit-sourced body byte equality
  + bounded public-archive observation
```

Each semantic commit has a focused GREEN. Task 4 also runs the complete
modified release and documentation-contract files so no intentionally failing
intermediate tree is committed. Full suites remain phase gates rather than
substitutes for RED-to-GREEN evidence.

### Code Quality, Performance, and Security

- **Code quality:** current/historical release ownership is separated instead
  of duplicating version-specific mutable truth. No new release framework,
  profile version, runtime helper, or dependency is introduced.
- **Performance:** no runtime hot path changes. Full non-Docker, Docker,
  frontend, and archive checks are bounded serial release costs.
- **Security:** no credential, provider, deployment, auth, or hosted surface is
  added. GitHub and archive responses are treated as untrusted until exact
  status, identity, type, path, and byte checks pass.
- **Data integrity:** migration 010 and application data are verify-only in
  this release. The only proven post-010 rollback remains complete backup
  restore plus exact old-revision verification with stopped writers.

### Error and Partial-State Matrix

| State | Result | Allowed rescue |
|---|---|---|
| wrong Phase A/B base or tree | block | new authority compatibility review |
| new dependency conflict | block | separate dependency decision |
| proof/check failure | block | evidence-derived targeted repair |
| tag absent, Release absent | eligible after authorization | create/push tag once, then Release |
| exact tag, Release absent | partial success | verify/fetch exact tag, then create Release |
| exact tag, exact Release | already persisted | readback only |
| tag/Release mismatch | block | separate public correction decision |
| transport/auth probe error | block | restore transport/auth; never infer absence |
| archive observation failure after publication | release remains public, closeout incomplete | retain evidence; separate patch/deprecation decision |

### Engineering Dual Voices

The independent Engineering voice and the authority's repo-level review agreed
on the two-PR architecture, no runtime/schema/dependency expansion, and the
need for exact Phase B and publication identities. Both independently found
the wrong protected hash, non-claim contradiction, hidden Task 4 version
coupling, and byte-readback bug. The bounded CLI voice timed out before a final
report; its repo-verifiable findings about the protected hash, baseline
identity, Release body, and plan hygiene were independently reproduced and
incorporated. It is marked `[codex-timeout]`, not treated as a second completed
approval.

### Engineering NOT in Scope

- changing `STRICT_ARGV`, profile/case/episode meaning, or consumer proof;
- runtime Agent, API, database, migration, frontend behavior, or dependencies;
- automated release/rollback, signing platform, SBOM platform, or deployment;
- provider/model/tool execution or another governed provider attempt;
- weakening public-safety, archive, hosted-check, or immutable-identity gates.

### Engineering Completion Summary

| Area | Result |
|---|---|
| Architecture | PASS after exact Phase A/B merge binding |
| Tests | PASS after three deterministic RED contradictions are removed |
| Error paths | PASS after closed publication resume states |
| Security | PASS after private marker and unsafe archive extraction are removed |
| Performance | PASS; release-only serial cost |
| Deployment | Not applicable; source publication only |
| Unresolved Engineering decisions | 0 |

### Book-Aligned Engineering Self-Review

The Harness remains the online execution boundary and produces evidence rather
than changing its own policy. Evaluation and Observability remain provider-free
offline verification inputs. The Loop release bridge changes only how an
immutable historical record is selected; it does not let one observed failure
become a permanent runtime rule. Candidate isolation, retained regressions,
human acceptance, immutable publication identity, and evidence-bound rollback
follow the book's continuous-evolution discipline without creating an
autonomous self-modifying system.

---

## AutoPlan Phase 3.5 — DevEx Review

Result: `PASS AFTER AMENDMENTS`. This is a documentation and release-operator
journey, not a new API, SDK, UI, or hosted product.

### Persona and Journey

Primary persona: an OSS maintainer or release operator who did not implement
the post-v0.1.6 features but must decide whether one exact candidate is safe to
publish and recover a partially completed publication without moving history.

```text
discover the release scope and limits
  -> verify one provider-free first result
  -> reproduce the pinned environment
  -> run Phase A RED/GREEN and retained gates
  -> review and merge the verifier bridge
  -> start Phase B from the exact merge SHA/tree
  -> run release-note/current-truth RED/GREEN
  -> freeze one exact release candidate
  -> merge with reviewed-tree equality
  -> re-bind the exact merge SHA/tree before publication
  -> classify absent/exact/mismatch tag and Release state
  -> publish once under separate human authorization
  -> read back tag/commit/tree/body
  -> observe the untrusted public archive safely
```

The operator's first meaningful result is the existing provider-free Loop
check:

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/evidence_gated_loop_gate.py check
```

Expected stable output:

```json
{"match":true,"record_status":"valid","status":"valid"}
```

This is the plan's "hello world": it proves that the retained Loop record is
coherent without credentials, a provider call, or publication authority. It
does not replace the full release matrix.

### TTHW Assessment

- Before this review: estimated `5-10 minutes` for a new maintainer to locate
  the core Loop and recovery gates across README/reference/CI surfaces.
- Target after implementation: `2-5 minutes` to find and run the first
  provider-free Loop result, then follow one explicit path to the complete
  release matrix.
- Measurement status: plan-stage estimate only. The implementation review must
  inspect the rendered README/reference links and copy the commands in a fresh
  shell; no analytics or hosted telemetry is added merely to measure TTHW.

### DevEx Findings and Resolutions

| Priority | Finding | Operator impact | Resolution |
|---|---|---|---|
| P0 | publication recomputed `RELEASE_COMMIT` from mutable `main` | a later main commit could be published without Phase B review | External Gate B now persists `EXPECTED_RELEASE_COMMIT/TREE`; Task 7 rejects main/tree drift |
| P0 | failed GitHub probes could return through command substitution without a hard shell stop | auth/transport failure could be mistaken for an actionable state | both probe assignments propagate nonzero status; only explicit HTTP 404 means absent |
| P1 | Phase B recorded an expected merge tree but did not consume it | maintainer could not directly prove reviewed-tree continuity | Phase B preflight now requires commit and tree identities |
| P1 | readback-only recovery did not state clearly that it still materializes the immutable release body | an operator could reach body comparison without `RELEASE_NOTES_FILE` | commit-sourced body materialization is unconditional; only `gh release create` is conditional |
| P1 | exact remote-tag/local-tag recovery had no copyable fetch command | partial publication recovery required improvisation | plan provides a single exact-ref fetch and requires object/peeled/tree equality |
| P1 | README required-CI inventories omitted the already-required Loop and recovery proof commands | the strongest release evidence was harder to discover than older gates | Task 5 adds value-equal English/Chinese entries and keeps the short first-result path |
| P2 | positive live-provider claim rejection covered only phrase-first grammar | verb-first overclaims could escape the release contract | both release-note and corpus contracts reject phrase-first and verb-first affirmative forms |
| P2 | CEO appendix still named a UTC date gate | operator prose disagreed with the actual Asia/Shanghai command | wording now matches the executable gate |

### Eight-Dimension Scorecard

| Dimension | Before | After | Evidence |
|---|---:|---:|---|
| Getting started | 7 | 8 | one provider-free first result plus direct README/reference discovery |
| API/CLI ergonomics | 8 | 8 | no new interface; existing fixed commands and JSON status remain |
| Errors and debugging | 6 | 8 | stable stop codes, explicit 404 rule, exact partial-state rescue |
| Documentation and learning | 7 | 9 | causal release opening, complete note, bilingual command inventory |
| Upgrade and migration | 7 | 9 | observation migration, migration 010 prerequisites, exact rollback |
| Environment and tooling | 7 | 8 | pinned 96-package gate, Docker ownership, archive isolation |
| Community and ecosystem | 6 | 7 | public immutable Release improves discovery; no unsupported ecosystem claim |
| Measurement and feedback loop | 8 | 9 | RED/GREEN, retained gates, exact CI/readback, bounded archive observation |

Overall plan-stage DX moves from approximately `7.0/10` to `8.3/10`. The
remaining gap to 10 is deliberate: this project does not add a hosted
playground, installer, analytics, signing service, or generalized release
platform for a source-release maintenance phase.

### Error and Recovery Quality

| Failure | What the operator sees | Correct next action |
|---|---|---|
| missing pinned environment | `DRA_PINNED_ENVIRONMENT_REQUIRED` | obtain separate environment creation/install authorization |
| Phase B commit/tree mismatch | `DRA_PHASE_B_BASE_MISMATCH` or `DRA_PHASE_B_BASE_TREE_MISMATCH` | return to authority compatibility review |
| preparation date drift | `DRA_V017_RELEASE_DATE_REVIEW_REQUIRED` | approve one replacement date across note/changelog/tests |
| publication main/tree drift | `DRA_V017_RELEASE_MAIN_DRIFT` or `DRA_V017_RELEASE_TREE_DRIFT` | do not tag; re-review the new immutable candidate |
| GitHub probe failure | `DRA_V017_PUBLICATION_PROBE_FAILED` | restore auth/transport and re-probe; never infer absence |
| exact tag without Release | explicit partial state | verify/fetch the exact tag, then create only the missing Release |
| archive observation failure | public release persists; closeout incomplete | retain evidence and make a separate patch/deprecation decision |

### DevEx Voices

The authority completed the eight-pass maintainer journey against the live
plan and repository. A bounded Codex CLI outside voice and a separate
read-only reviewer were both terminated after exceeding the time budget
without returning a final report. They are recorded as `[codex-timeout]` and
`[reviewer-timeout]`; neither is represented as an approval or dual-confirmed
finding. Repo-verifiable issues surfaced before timeout were independently
reproduced before inclusion.

### DevEx NOT in Scope

- changing the runtime CLI/API, adding an installer, dashboard, playground, or
  hosted telemetry;
- adding release automation, auto-remediation, analytics, signing, SBOM, or
  deployment;
- changing profile/case/episode semantics or generating new consumer proof;
- weakening exact identity, public-safety, Docker, archive, or human approval
  gates to reduce steps.

### Book-Aligned DevEx Self-Review

The maintainer journey follows the book's Harness and Evaluation boundary:
commands expose bounded, inspectable evidence; they do not grant release
authority. The offline path composes trajectories, retained regressions, and
consumer evidence into a candidate decision, while human approval controls
merge, tag, Release, and rollback. Debuggability comes from stable codes and
immutable identities rather than unbounded traces. No one failed run becomes
a permanent runtime rule.

---

## Cross-Phase Themes

1. **Historical authority is immutable; current truth is mutable.** Phase A
   removes the accidental root-version dependency without changing the
   historical subject or versioned verification contract.
2. **A candidate cannot authorize its own verifier.** Phase A is reviewed,
   hosted-tested, and merged before Phase B begins from its exact merge
   identity.
3. **Online work produces evidence; offline work decides.** The release packages
   existing Evidence, Evaluation, retained consumer proof, and recovery proof;
   it adds no runtime self-modification.
4. **External partial success is a first-class state.** Tag push, Release
   creation, and archive observation are reconciled from persisted state, not
   blindly retried.
5. **Release and rollback remain human authority.** Every irreversible public
   action has its own authorization and immutable identity readback.

## Decision Audit Trail

| Decision | Owner | Evidence | Result |
|---|---|---|---|
| Publish a bounded v0.1.7 pack instead of adding another feature | user | post-v0.1.6 merged reliability/evaluation/Loop/recovery surface | approved direction |
| Use separate verifier and candidate PRs | user + authority | fixed selector otherwise judges a version it is changed with | approved architecture |
| Classify the selector repair as narrow compatible maintenance | authority | profile ID/version/argv/coverage/failure/case/episode semantics unchanged | spec clarified and reviewed |
| Keep consumer proof commit-pinned | authority | existing Night Voyager proof names the exact producer tuple | no re-pin or tag-acceptance claim |
| Keep publication and rollback human-owned | user + authority | Loop episodes retain historical `hold`; ADR assigns release authority to review | separate merge/tag/Release gates |
| Skip Design Review | authority | no UI or end-user interaction change | not applicable |
| Stop external review voices after bounded time | authority | neither produced a final report; user explicitly rejects wasteful waiting | timeouts recorded, no false consensus |

No user taste choice remains inside implementation. The user approved this
complete plan; mechanical landing and authority actual-diff review now gate
Phase A implementation.

## Implementation Tasks

- [ ] **Phase A / Task 1:** make the fixed v0.1.6 selector a pure immutable
  historical authority with fail-to-pass byte-drift controls.
- [ ] **Phase A / Task 2:** update only the bounded maintenance wording,
  regenerate canonical Loop projections, and prove structural equality outside
  that wording.
- [ ] **Phase A / Task 3:** run retained provider-free, full non-Docker, Docker,
  frontend, presentation, identity, and exact-scope gates; stop for authority
  review.
- [ ] **External Gate A:** publish, review, hosted-test, and squash-merge the
  verifier bridge; persist exact merge commit/tree.
- [ ] **Phase B / Task 4:** create the complete v0.1.7 release contract and
  coherent release identity from the exact Phase A merge.
- [ ] **Phase B / Task 5:** move current public truth atomically, preserve
  historical notes, and expose the complete bilingual proof inventory and
  migration/rollback/non-claim boundaries.
- [ ] **Phase B / Task 6:** run the complete release matrix and local
  exact-commit archive smoke; stop for authority review.
- [ ] **External Gate B:** publish, review, hosted-test, and squash-merge the
  release candidate; persist exact release commit/tree.
- [ ] **Task 7:** after a separate authorization, reconcile tag/Release state,
  create only missing public objects, and read back exact identity/body.
- [ ] **Task 8:** safely inspect the public source archive, record transport
  evidence, and return for separately authorized local cleanup.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|---|---|---|---:|---|---|
| CEO Review | `/plan-ceo-review` | Scope and release strategy | 1 | CLEAR AFTER AMENDMENTS | bounded release retained; verifier/current-truth, date, changelog, and non-claim gaps closed |
| Codex Review | outside CLI voices | Independent second opinion | 3 | TIMEOUT | no final reports; repo-verifiable fragments were independently reproduced |
| Eng Review | `/plan-eng-review` | Architecture, tests, security, publication | 1 | CLEAR AFTER AMENDMENTS | hash, test ownership, exact bases, probe, archive, and partial-publication gaps closed |
| Design Review | `/plan-design-review` | End-user UI/UX | 0 | SKIPPED | no UI or visual interaction surface |
| DX Review | `/plan-devex-review` | Maintainer and release-operator journey | 1 | CLEAR AFTER AMENDMENTS | TTHW, discovery, exact release identity, probe propagation, and recovery actions closed |

**CODEX:** Outside CLI attempts timed out and are not counted as approvals.

**CROSS-MODEL:** No completed cross-model consensus is claimed; the review
authority reproduced every accepted finding against live files and commands.

**VERDICT:** CEO + ENG + DX CLEARED — complete plan approved; ready for
mechanical landing and authority actual-diff review before Phase A
implementation. External publication remains unauthorized.

NO UNRESOLVED DECISIONS
