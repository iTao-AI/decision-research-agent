# Reproduce findings consumption from a source archive

This local method was verified on 2026-10-06 against source commit
`0be49fec33be42d424b2f70ddb3c3dcd1e10af31`, tree
`bbcdf2fd84b953fef8b2c733ef29a437878b198a`, with Python 3.11.15.
The [selected evidence record](../evidence/source-archive-findings-reproduction-v1.json)
contains actual archive/environment identities and four observed outcomes.

The asset is a complete tracked **source archive**. This revision has no
`pyproject.toml`, `setup.py`, `setup.cfg` or `MANIFEST.in`; running the extracted
source does not establish a wheel or installed application-package result.
`VERSION` contains `0.1.9`; that is source metadata, not a new release claim.

The producer uses the existing bounded native fixture entry. Programmed model
and source responses traverse the installed graph, application execution,
fenced finalization and persisted public readers. The CLI and separate
consumer read that service over real loopback HTTP. The method proves
structural consumption and process boundaries. Truth, entailment, autonomous
research quality and human value are not measured; Evidence stays unverified.

## Prepare the exact asset and isolated environment

Use an existing Python 3.11.15 runtime and a new task-owned directory.
Stop if any prerequisite command fails. Do not reuse an earlier data directory,
copy modules over the archive, set `PYTHONPATH` to a checkout, use an editable
install or load a local `.env`.

From a repository containing the exact commit:

```bash
unset PYTHONPATH PYTHONHOME
export PYTHONNOUSERSITE=1
python3.11 -c 'import sys; sys.exit(0 if sys.version_info[:3] == (3, 11, 15) else "Python 3.11.15 is required")'
mkdir -p output
DRA_REPRO_DIR="$PWD/output/source-archive-findings"
mkdir "$DRA_REPRO_DIR"
git archive --format=tar --prefix=decision-research-agent/ \
  --output="$DRA_REPRO_DIR/source.tar" \
  0be49fec33be42d424b2f70ddb3c3dcd1e10af31
git get-tar-commit-id < "$DRA_REPRO_DIR/source.tar"
shasum -a 256 "$DRA_REPRO_DIR/source.tar"
tar -xf "$DRA_REPRO_DIR/source.tar" -C "$DRA_REPRO_DIR"
python3.11 -m venv "$DRA_REPRO_DIR/venv"
"$DRA_REPRO_DIR/venv/bin/python" -m pip --isolated \
  --disable-pip-version-check install --no-deps \
  --index-url https://pypi.org/simple \
  -r "$DRA_REPRO_DIR/decision-research-agent/constraints.txt"
```

For that exact prefix and revision, the tar has 9,492,480 bytes and SHA-256
`ed3c4139951a9f8448974b901b02189f97065fdc8e87a022a51e7c7204359718`.
Its embedded Git commit must match. The archive contains 522 source files,
9,051,342 source bytes, 521 ordinary files and one executable. Every extracted
file's Git blob and executable bit matched the revision in the recorded run.
No local credentials, runtime stores, virtual environment, bytecode,
`node_modules`, raw receipts or ignored sessions were in the archive.

The complete constraints file has SHA-256
`180a3b0986ac793d46ad47497d8abb990b38fd75d73ce0289bb652ca366565e7`.
All 97 pinned distributions matched their installed versions in the fresh
environment; only its bootstrap `pip` and `setuptools` were outside that lock.
Run the existing compatibility gate:

```bash
"$DRA_REPRO_DIR/venv/bin/python" \
  "$DRA_REPRO_DIR/decision-research-agent/scripts/check_dependency_compatibility.py"
```

For this lock it returns `{"status":"approved_diagnostic"}`. This is the
existing narrowly approved `ragflow-sdk==0.13.0` / `pytest==9.0.3` metadata
diagnostic, not an assertion that plain `pip check` has no diagnostics.
Other incompatibilities fail the gate. The [checker](../../scripts/check_dependency_compatibility.py)
defines its exact closed exception.

Unset `PYTHONPATH` and `PYTHONHOME`, disable user-site loading, and run from the
extracted source root. Project module locations must resolve inside that
archive; installed dependency locations must resolve inside the new venv.
The recorded run checked `api`, `agent`, `tools`, `scripts` and DeepAgents
locations and confirmed user-site isolation.

## Start the existing fixture service

In terminal A, set the same absolute `DRA_REPRO_DIR` and choose a free loopback
port. The example uses 8876; use another free port consistently if needed.

```bash
mkdir "$DRA_REPRO_DIR/fresh-tmp" "$DRA_REPRO_DIR/receipts"
cd "$DRA_REPRO_DIR/decision-research-agent"
unset PYTHONPATH PYTHONHOME
PYTHON_DOTENV_DISABLED=1 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 \
  LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false LANGCHAIN_TRACING=false \
  TMPDIR="$DRA_REPRO_DIR/fresh-tmp" \
  "$DRA_REPRO_DIR/venv/bin/python" scripts/research_evidence_delivery_proof.py \
  serve --origin http://127.0.0.1:5175 --port 8876 --seconds 180
```

This entry creates a fresh temporary application store and seeds four real
executions. It retains the existing fixture-only request admission, removes
provider credentials and denies external runtime transports and provider
fallbacks. It is not the ordinary real-provider launcher. Dependency
installation above is a separate preparation step.

Monitor lines precede the startup JSON containing `api` and `cases`; use that
metadata line to identify this service's run IDs. Do not parse the first stdout
line as JSON or attach an older database just because synthetic IDs repeat.
The existing producer's successful startup requires its independently declared
four-case structural expectations to pass.

## Read and retain the observed delivery

In terminal B, set the same `DRA_REPRO_DIR`. Use the CLI from the extracted
source and a run ID printed by this service:

```bash
cd "$DRA_REPRO_DIR/decision-research-agent"
DRA_REPRO_API=http://127.0.0.1:8876
DRA_REPRO_RUN=run_e4383ba9ee7353e89f6cc82563dd1470
unset PYTHONPATH PYTHONHOME
PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=ascii \
  "$DRA_REPRO_DIR/venv/bin/python" tools/decision_research_agent_tool.py \
  --base-url "$DRA_REPRO_API" --timeout 3 findings \
  --run-id "$DRA_REPRO_RUN" > "$DRA_REPRO_DIR/receipts/partial-cli.json"
PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=ascii \
  "$DRA_REPRO_DIR/venv/bin/python" tools/decision_research_agent_tool.py \
  --base-url "$DRA_REPRO_API" --timeout 3 findings \
  --run-id "$DRA_REPRO_RUN" --format markdown \
  > "$DRA_REPRO_DIR/receipts/partial-report.md"
PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=ascii \
  "$DRA_REPRO_DIR/venv/bin/python" scripts/research_findings_consumer.py \
  --base-url "$DRA_REPRO_API" --timeout 3 --run-id "$DRA_REPRO_RUN" \
  --output "$DRA_REPRO_DIR/receipts/partial-consumer.json"
```

The three commands exit 0. `partial-consumer.json` retains two questions, one
candidate disposition, one unresolved disposition with its reason, one same-run
reference and the actual unverified state. Consumer output targets must be new;
the consumer refuses overwrites.

The [CLI reference](../reference/research-findings-cli.md) defines exact
response, encoding, timeout and error behavior. JSON stdout is a presentation
of the public delivery package; the canonical JSON bytes are
`artifact.content.encode("utf-8")`, whose SHA-256 must equal `artifact.content_hash`.
The parsed content must equal `report`. Markdown stdout must equal the result
reader's `artifact.content.encode("utf-8")` byte-for-byte, including its own hash
and newline behavior. Valid Unicode is preserved even with the process encoding
set to ASCII; a fixture need not contain a particular glyph.

Read `/api/runs/{run_id}` before and after consumption. The recorded public
business observations were unchanged. The consumer reads public HTTP through
the real CLI child; database, workspace, candidate and trace data do not supply
its assertions. Canonical source references retain exact code-point excerpt
offsets, observed snippets, source identity/fingerprint and current-run Evidence.

| Case | Questions / candidate / unresolved | References / reported contradictions | CLI JSON / Markdown / consumer exit |
| --- | --- | --- | --- |
| complete | 1 / 1 / 0 | 1 / 0 | 0 / 0 / 0 |
| partial | 2 / 1 / 1 | 1 / 0 | 0 / 0 / 0 |
| contradictory | 1 / 1 / 0 | 2 / 1 | 0 / 0 / 0 |
| insufficient-evidence | 1 / 0 / 1 | 0 / 0 | 1 / 1 / 1 |

For the insufficient case, use this service's
`run_d057d451d4785220aa34d5887f3e061d`. All three reads return
`run_delivery_blocked`; the consumer creates no success receipt. Findings and
Markdown HTTP readers return 409. Keep that outcome as a failure, without
waiting, rerunning research, delivering an empty report or falling back to generic.

Stop the owned service with Ctrl-C; the timer also expires automatically.
The recorded stop returned 130 after cleanup, released its port, and left all
522 source files and modes unchanged. Retain raw HTTP/CLI/process receipts,
artifact bytes, environment/import inventories and task data in an ignored
directory. The selected evidence record is structural proof with the limits
above; it does not change Evidence or review/verification authority.

See the [producer walkthrough](research-evidence-delivery.md), the
[independent consumer implementation](../../scripts/research_findings_consumer.py)
and the existing [process/HTTP regressions](../../tests/integration/test_research_findings_consumer_journey.py).
