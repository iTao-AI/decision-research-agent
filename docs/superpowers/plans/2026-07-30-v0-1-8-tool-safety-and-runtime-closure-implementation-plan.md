# Decision Research Agent v0.1.8 Tool Safety and Runtime Closure Implementation Plan

Status: Approved implementation mandate. Implementation begins in an isolated
worktree. Push, PR, merge, annotated tag, and GitHub Release are permitted only
through the exact-head gates below. Deployment is excluded.

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:executing-plans` to implement this plan task-by-task. Use
> `superpowers:test-driven-development` for every behavior change,
> `superpowers:systematic-debugging` for any unexpected failure, and
> `superpowers:verification-before-completion` before each READY or publication
> claim. Do not use subagent-driven development or parallel implementation
> lanes: the SQL scanner, error projector, pool lifecycle, Compose proof, and
> release truth share contracts and must advance serially.

**Goal:** Correct the bounded MySQL authority/query/lifecycle gaps, close raw
runtime exception egress, prove the exact no-deps dependency closure, and ship
the result as an immutable provider-free `v0.1.8` patch release.

**Architecture:** A project-owned SQL scanner admits one safe `SELECT`/CTE and
produces an application-owned bounded statement. A real SELECT-only MySQL
principal and startup `SHOW GRANTS` attestation remain the execution authority.
A shared stable error projection controls exception egress across tool,
harness, task, API, WebSocket, monitor, telemetry, and artifact boundaries.
Connector/Python's public pooled-wrapper `close()` owns pool return. The
no-deps lock adds only the missing SQLAlchemy transitive closure and verifies
`pip check` through an exact allowlist.

**Tech Stack:** Python 3.11; MySQL 8.0 official image; Connector/Python 9.7.0;
SQLAlchemy 2.0.51; greenlet 3.5.4; LangChain/DeepAgents/LangGraph pinned by
`constraints.txt`; pytest 9.0.3; Docker Compose; GitHub Actions; Node 24/npm;
GitHub pull requests, annotated tags, and Releases.

## 1. Frozen inputs and source authority

- Approved spec path:
  `docs/superpowers/specs/2026-07-30-v0-1-8-tool-safety-and-runtime-closure-design.md`.
- Original clean planning baseline:
  `main@4d1ba5e2d80584e0240abcea4be74fa4ec891eb0`.
- Immutable prior release: annotated `v0.1.7`; do not edit/move/delete it or
  rewrite its tracked release note.
- Connector/Python authority: official source tag `9.7.0`, commit
  `cbac6da551e915605575989551b3b7c803d74a0c`.
  `PooledMySQLConnection.close()` resets the underlying connection, calls its
  pool's `add_connection()` with that underlying connection, then clears the
  wrapper. Application code therefore calls wrapper `close()` and never calls
  the pool directly.
- MySQL authority: the official `mysql:8.0` entrypoint creates a configured
  `MYSQL_USER` with `GRANT ALL` and initializes scripts only on an empty data
  directory. Therefore this patch does not set `MYSQL_USER`/`MYSQL_PASSWORD` on
  the server service and does not rely on `/docker-entrypoint-initdb.d` for
  existing volumes.
- MySQL query-time authority: official MySQL 8.0
  `MAX_EXECUTION_TIME(N)` optimizer hint applies to read-only `SELECT` and
  error `3024` (`ER_QUERY_TIMEOUT`) denotes termination. The application owns
  the inserted hint; user comments are rejected.
- SQLAlchemy metadata authority: `SQLAlchemy==2.0.51` requires `greenlet>=1`
  on supported Linux aarch64/x86_64/amd64. The pinned dependency owners are
  `langchain-community==0.4.2` and `langchain-classic==1.0.8`.
- Greenlet authority: `greenlet==3.5.4` supports Python 3.11 and publishes the
  supported Linux/macOS wheels. It is a transitive lock closure, not a new
  direct product dependency.
- pip authority: `python -m pip check` returns zero for a compatible
  environment and nonzero for missing or incompatible requirements. This repo
  accepts only clean output or one parsed RAGFlow/pytest diagnostic.

## 2. Global constraints

- Work only on a short `codex/` branch in the execution task's isolated
  worktree. Do not edit the primary DRA checkout.
- Before editing, read the worktree's full applicable `AGENTS.md`, confirm its
  start commit, branch, full status, other worktrees, and remote `main`.
- Mechanically land this spec and plan first. Their content must be
  public-neutral and must not contain private coordination identity, private
  workspace paths, credentials, personal rationale, or local restore data.
- Do not install or configure host tools, Skills, plugins, MCP, GBrain, or
  hosted services. The primary checkout has no approved `.venv`; use a
  task-owned locked backend image for local Python test execution. Docker
  package installation remains confined to the task-owned image and uses the
  checked-in exact lock.
- Do not read credential values beyond the synthetic task-owned fixtures
  created by tests. Never run a provider/model/search/tool request, remote
  LangSmith tracing, `observe-live`, deploy, or a business database mutation.
- Docker preflight must record host space, engine availability and Docker VM
  space before building. Use a unique Compose project and exact labels. Do not
  restart/configure Docker Desktop or run system/image/builder/volume prune.
- Only task-owned containers, networks, named volumes, images, and temporary
  paths may be removed. Preserve task-owned resources until failure evidence
  is collected, then use bounded exact cleanup.
- `v0.1.7` tag, GitHub Release, release body, and tracked release note are
  immutable. Historical notes `v0.1.0` through `v0.1.7` remain byte-identical.
- Keep the known `ragflow-sdk==0.13.0` / `pytest==9.0.3` metadata mismatch. Do
  not upgrade/downgrade either distribution or normalize its declaration.
- Do not add a SQL parser, ORM, DB framework, runtime service, or direct
  `greenlet` product import. No broad exception cleanup outside affected
  external-tool/harness/task flows.
- Repository docs remain English unless an existing paired Chinese surface is
  updated. PR title/body are Simplified Chinese with `Summary`, `Completion`,
  and `Verification` in result-first order.
- Stage explicit paths only. Do not use `git add .` or `git add -A`. Commit
  coherent TDD slices; no WIP/micro commit and no publication before authority
  review.

## 3. Target data flow and ownership

```text
Compose env
  ├─ root + database ──> mysql
  ├─ root + app creds ─> mysql-bootstrap (one shot, exact grants)
  └─ app creds only ───> backend
                               │
                               v
                    direct preflight connection
                    CURRENT_USER + SHOW GRANTS
                               │ exact SELECT-only
                               v
                         connector pool
                               │
model query -> lexical scanner -> bounded SQL (hint + LIMIT <= 101)
                               │
                               v
                    fetchmany(25) -> CSV <= 64 KiB
                               │
                    fixed ToolMessage / canonical result
                               │
exception -> stable projector -> code + fixed message + class + correlation
                               ├─ logger
                               ├─ monitor / telemetry
                               ├─ model ToolMessage
                               ├─ canonical artifact
                               └─ REST / WebSocket
```

Authority rules:

1. Lexical admission is a defense-in-depth input contract; MySQL grants are
   mutation authority.
2. Application DB state remains business authority. Monitor, telemetry,
   exception class, and correlation IDs are diagnostic only.
3. Successful tool output remains model/artifact content authority. Exception
   objects and raw messages are never content authority.
4. Connector/Python's pooled wrapper owns pool return. The application owns
   bounded cursor drain/close before wrapper close.
5. Human review owns PR merge, tag, Release, and rollback. No test or runtime
   path can publish itself.

## 4. Planned file surface

### Design and plan

- Create:
  `docs/superpowers/specs/2026-07-30-v0-1-8-tool-safety-and-runtime-closure-design.md`
- Create:
  `docs/superpowers/plans/2026-07-30-v0-1-8-tool-safety-and-runtime-closure-implementation-plan.md`
- Modify: `docs/superpowers/README.md`

### Runtime contracts

- Create: `tools/error_projection.py`
  - closed codes, fixed model-visible messages, exception-class-only
    diagnostics, connector errno classification, safe logger helper.
- Create: `tools/sql_read_only.py`
  - lexical scanner, governing-SELECT/top-level-LIMIT positions, safe bounded
    statement construction, query timeout configuration.
- Modify: `tools/db_connection.py`
  - direct grant attestation, pool creation, stable errors, public wrapper
    close exactly once.
- Modify: `tools/mysql_tools.py`
  - scanner integration, bounded fetch/serialization, stable errors, resource
    release.
- Modify: `tools/ragflow_tools.py`
- Modify: `tools/tavily_tools.py`
  - stable tool results and safe retry/cleanup logging.
- Modify: `agent/deepagents_harness.py`
- Modify: `api/research_execution_service.py`
- Modify: `api/task_tracker.py`
  - fixed framework/task messages, exception class/correlation diagnostics,
    no raw traceback/message.

### Container and dependency closure

- Create: `scripts/mysql_read_only_bootstrap.sh`
- Create: `scripts/check_dependency_compatibility.py`
- Modify: `docker-compose.yml`
- Modify: `Dockerfile.backend`
- Modify: `constraints.txt`
- Modify: `.github/workflows/ci.yml`
- Modify: `.env.example`
- Modify: `scripts/secure_local_runtime_proof.py`
- Modify: `scripts/secure_local_runtime_contracts.py` only if the existing
  closed evidence schema requires new bounded fields/case values.
- Modify: `scripts/bounded_live_producer_lifecycle.py`
- Modify: `tests/integration/test_bounded_live_producer_container.py`
- Modify generated secure-runtime evidence only through its canonical builder:
  `docs/evidence/secure-local-runtime-v1.json` and
  `docs/evidence/secure-local-runtime-v1.md`.

### Unit and integration tests

- Create: `tests/unit/test_error_projection.py`
- Create: `tests/unit/test_sql_read_only.py`
- Create: `tests/unit/test_dependency_compatibility.py`
- Create: `tests/integration/test_runtime_error_projection.py`
- Modify: `tests/unit/test_db_connection.py`
- Modify: `tests/unit/test_mysql_tools.py`
- Modify: `tests/unit/test_ragflow_tools.py`
- Modify: `tests/unit/test_tavily_tools.py`
- Modify: `tests/unit/test_deepagents_harness.py`
- Modify: `tests/unit/test_research_execution_service.py`
- Modify: `tests/unit/test_task_tracker.py`
- Modify: `tests/unit/test_secure_local_container_contracts.py`
- Modify: `tests/unit/test_bounded_live_producer_lifecycle.py`
- Modify: `tests/integration/test_secure_local_runtime_proof.py`
- Modify: `tests/integration/test_observation_delivery.py` only where the new
  aggregate sink negative control can reuse its real monitor/WebSocket harness.
- Modify: `tests/unit/test_deployment_preflight.py`
- Modify documentation contract tests that own changed public wording.

### Current docs and patch release

- Modify: `README.md`
- Modify: `README_CN.md`
- Modify: `SECURITY.md`
- Modify: `CHANGELOG.md`
- Modify: `docs/README.md`
- Modify: `docs/getting-started.md` if it states the old MySQL/query contract.
- Modify: `docs/operations/secure-local-runtime.md`
- Modify: `docs/reference/external-services.md`
- Modify: `docs/reference/observation-contract.md`
- Modify: `tests/unit/test_release_metadata.py`
- Create: `tests/unit/test_v0_1_8_release_metadata.py`
- Create: `docs/releases/v0.1.8.md`
- Modify: `VERSION`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json` root package version only.

Files outside this inventory require an explicit same-contract reason in the
execution receipt. Any new database/runtime architecture file or dependency is
an unresolved scope expansion and stops implementation.

## 5. Task 0 — Land the approved design and establish immutable baselines

**Files:** approved spec, this plan, `docs/superpowers/README.md`.

1. Read all applicable rules and inspect:

```bash
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git rev-parse origin/main
git status --porcelain=v1 --untracked-files=all
git worktree list --porcelain
git tag --points-at HEAD
gh pr list --state open --json number,title,headRefName,headRefOid,baseRefName,url
```

Expected start commit is the planning baseline unless `main` legitimately
advanced before worktree creation. If it advanced, stop before editing and
return the exact new commit/diff to authority; do not silently rebase the plan.

2. Create a short `codex/v0-1-8-tool-safety-runtime-closure` branch if the
worktree setup did not already provide an appropriate branch.

3. Mechanically write the exact approved spec and plan, link them from the
Superpowers index, and run:

```bash
git diff --check
PRIVATE_ROOT='/''Users''/'
PRIVATE_TASK_PREFIX='019''f'
if rg -n "${PRIVATE_ROOT}|${PRIVATE_TASK_PREFIX}[0-9a-f-]{20,}" \
  docs/superpowers/specs/2026-07-30-v0-1-8-tool-safety-and-runtime-closure-design.md \
  docs/superpowers/plans/2026-07-30-v0-1-8-tool-safety-and-runtime-closure-implementation-plan.md \
  docs/superpowers/README.md; then
  exit 1
fi
```

Expected: `git diff --check` succeeds and the marker scan has no matches.

4. Record SHA-256 for the exact spec and plan in the implementation receipt,
then commit one design/plan landing commit.

## 6. Task 1 — Close the no-deps runtime lock and fail-closed pip diagnostic

**Files:** `constraints.txt`, `scripts/check_dependency_compatibility.py`,
`Dockerfile.backend`, `.github/workflows/ci.yml`,
`tests/unit/test_dependency_compatibility.py`,
`tests/unit/test_deployment_preflight.py`, affected docs/tests.

**Interfaces:**

- `APPROVED_RAGFLOW_DIAGNOSTIC`: semantic tuple of package/version,
  requirement, installed package/version; no substring-only allowlist.
- `parse_pip_check(stdout: str, stderr: str, returncode: int) -> tuple[...]`
  accepts zero with empty success output or returncode one with exactly one
  anchored diagnostic matching the approved tuple. Any other line, missing
  package diagnostic, stderr, invalid UTF-8 (at subprocess boundary), or
  returncode fails.
- CLI `python scripts/check_dependency_compatibility.py` runs
  `sys.executable -m pip check`, prints one stable JSON line, and exits 0 only
  for `clean` or `approved_diagnostic`.

### RED

Write tests proving:

- `greenlet==3.5.4` is absent from the current lock;
- clean pip output is accepted;
- the exact known RAGFlow diagnostic is accepted regardless of the two
  specifier orderings pip may render;
- a second line, wrong package/version, missing dependency, stderr, or a
  near-match is rejected;
- CI and Dockerfile currently lack the gate and therefore fail contract tests.

Run inside the task-owned Python test image described in Task 8:

```bash
python -m pytest -q \
  tests/unit/test_dependency_compatibility.py \
  tests/unit/test_deployment_preflight.py
```

Expected: failures identify the missing pin/checker/gates, not import setup.

### GREEN

1. Add exactly `greenlet==3.5.4` in normalized alphabetical lock order. Do not
   change `requirements.txt` or any other pin.
2. Implement the checker with `subprocess.run([...], shell=False)`, bounded
   captured output, no network, and a stable JSON result.
3. After `pip install --no-deps -r constraints.txt`, run the checker in both
   backend and container CI jobs. Keep it before proofs/tests.
4. Copy only `scripts/check_dependency_compatibility.py` into its final image
   path before the checker, run it after dependency install, then retain the
   existing later selective `COPY scripts/ scripts/`. Do not broaden the build
   context or invalidate dependency caching for unrelated script edits.
5. Add an image/CI import proof for `greenlet`, `sqlalchemy`,
   `langchain_community`, and `langchain_classic`.
6. Re-run the RED tests. Inspect `git diff -- constraints.txt` to prove no
   second pin changed.

Rollback: remove the one pin, checker, and exact CI/Docker calls together. A
partial rollback that retains a conflict-free claim is forbidden.

## 7. Task 2 — Introduce the closed stable-error projection

**Files:** `tools/error_projection.py`,
`tests/unit/test_error_projection.py`.

**Interfaces:**

```python
@dataclass(frozen=True)
class ErrorProjection:
    code: Literal[...closed codes...]
    message: str
    error_type: str

def classify_exception(exc: BaseException, *, operation: str) -> ErrorProjection: ...
def safe_log(logger, level: int, *, event: str, projection: ErrorProjection,
             correlation: str | None = None, attempt: int | None = None) -> None: ...
```

- Classification uses exception class and connector attributes such as `errno`
  and SQLSTATE; it never reads `str(exc)` or `exc.args`.
- Fixed model-visible messages are selected by operation and code from a closed
  mapping. Each is bounded (target <= 160 UTF-8 bytes) and contains no user
  value.
- Error type is an allowlisted class-name shape; an exotic dynamic class name
  falls back to `Exception`.
- `safe_log` uses a constant format plus scalar arguments. It never passes
  `exc_info` or the exception.

### RED

Use a hostile exception whose `__str__`, `args`, path, query, secret marker,
and traceback all contain `DRA_ERROR_EGRESS_SENTINEL`. Prove no classifier or
logger path evaluates hostile `__str__`, output is stable, class/code remain,
and unsupported operations/codes fail closed.

### GREEN

Implement the smallest dependency-free module and rerun the tests. Do not add
an adapter hierarchy, registry framework, or serialization schema.

## 8. Task 3 — Build one-statement read-only SQL and result-budget contracts

**Files:** `tools/sql_read_only.py`, `tests/unit/test_sql_read_only.py`.

**Interfaces:**

```python
@dataclass(frozen=True)
class ReadOnlyStatement:
    sql: str
    timeout_ms: int
    max_rows: int = 100
    fetch_batch_rows: int = 25
    max_serialized_bytes: int = 65_536

class SqlAdmissionError(ValueError):
    code: Literal["input_invalid", "unsafe_statement"]

def admit_read_only_query(query: str, *, environ: Mapping[str, str]) \
        -> ReadOnlyStatement: ...
```

Scanner requirements:

- one linear pass over at most a documented bounded query length; reject above
  the bound before token allocation;
- track single/double/backtick quotes, backslash/doubled quote escape,
  parentheses depth, and token spans;
- reject NUL, unbalanced state, outside-literal comments (`#`, `--` followed by
  whitespace/control, `/*`), delimiters, or internal semicolons;
- first depth-zero keyword is `SELECT` or `WITH`; for `WITH`, locate the
  governing depth-zero `SELECT` after complete CTE definitions;
- reject closed dangerous token/phrase/function set from the spec;
- detect only depth-zero `LIMIT`; accept numeric `LIMIT n`, `LIMIT offset,n`,
  or `LIMIT n OFFSET offset`; tighten the row count to 101; reject ambiguous or
  repeated depth-zero limit;
- inject one application-owned `/*+ MAX_EXECUTION_TIME(N) */` immediately
  after the governing `SELECT`; input comments are already forbidden;
- return SQL without a terminal user semicolon.

### RED matrix

- compatible: ordinary select, union, nested select, quoted keyword,
  semicolon-in-literal, escaped quote, one terminal semicolon, CTE, recursive
  CTE, numeric limit forms;
- reject: empty/whitespace, overlength, two statements, comment smuggling,
  delimiter, unbalanced state, SELECT INTO variants, DML/DDL/DCL/TCL/session,
  stored program/dynamic SQL/file/lock/resource functions, locking reads,
  WITH whose governing operation is not SELECT, repeated/ambiguous limit;
- prove governing hint and outer limit placement for SELECT, UNION, and CTE;
- prove `MYSQL_QUERY_TIMEOUT_MS` default 5000, boundaries 100 and 30000, and
  rejection of missing-format/out-of-range values.

### GREEN

Implement with standard library only. Do not use regex-only normalization,
`sqlparse`, or a database round trip. Re-run the full matrix and add property-
shaped parametrization for whitespace/case without adding a fuzzing dependency.

## 9. Task 4 — Align the connection manager with real grant and pool contracts

**Files:** `tools/db_connection.py`, `tests/unit/test_db_connection.py`.

**Interfaces and state:**

- Manager state is `uninitialized -> attesting -> ready` or
  `uninitialized/attesting -> failed`. Repeated `create_pool()` after ready is
  idempotent; after a failed attestation it does not construct a pool.
- `_attest_read_only_principal()` uses one direct connector connection, one
  cursor, `SELECT CURRENT_USER()`, and `SHOW GRANTS FOR CURRENT_USER()`.
- Grant parser accepts exactly one optional `USAGE ON *.*` and exactly one
  `SELECT ON <configured_database>.*` for the same current principal. It rejects
  role/default-role lines, global or other-schema grants, additional privilege,
  `WITH GRANT OPTION`, duplicates, malformed rows, and missing SELECT.
- Preflight cursor and direct connection close in nested `finally` blocks. Raw
  grant/principal/password/connector text never appears in return or logs.
- Pool config retains exact connector timeouts and size 5.
- `release_connection(connection)` calls the wrapper's public `close()` once
  regardless of `_pool` identity. It does not call `_pool.add_connection`.

### RED

Replace the lifecycle-inventing `MagicMock` expectation with small faithful
fakes that expose `close_count`, cursor rows, and pool construction count.
Prove exact grants pass, every additional/missing/malformed grant fails before
pool construction, preflight resources close, raw sentinel never egresses, and
pooled release calls only wrapper close. Add `KeyboardInterrupt`/BaseException
cleanup tests.

### GREEN

Implement the manager with stable `ErrorProjection` results. Preserve the
existing public return-string compatibility where callers require it, but the
strings must be fixed and query/exception-free. Keep original exceptions
chained only when raising an internal typed error.

## 10. Task 5 — Integrate bounded MySQL execution and public connector release

**Files:** `tools/mysql_tools.py`, `tests/unit/test_mysql_tools.py`.

**Interfaces:**

- custom query calls `admit_read_only_query` before `_ensure_pool`;
- cursor is unbuffered and reads only `fetchmany(25)` until the server-capped
  result of at most 101 rows is drained;
- standard-library CSV writer serializes header/rows incrementally;
- total UTF-8 output, including fixed trailer, never exceeds 65,536 bytes;
- fixed trailer:
  `[result_truncated code=result_truncated reason=<reason>
  rows_returned=<n> max_rows=100 max_serialized_bytes=65536]` on one line
  (implementation may omit the visual line break above; tests freeze exact
  bytes);
- timeout result contains stable `code=timeout` and `max_execution_ms`, no
  server text/query;
- normal empty/small result strings remain byte-compatible unless correct CSV
  quoting is required by a cell containing comma/quote/newline;
- all three MySQL tools use stable errors and pooled wrapper close exactly once.

### RED

Prove:

- validation occurs before connection acquisition;
- execution receives only the bounded/hinted SQL;
- no `fetchall()` occurs on custom-query path;
- fetch batch never exceeds 25 and server result is drained to <=101;
- exact 100-row success versus 101-row truncation;
- byte-limit and combined-limit trailers and total byte ceiling;
- commas, quotes, newlines, Unicode, `None`, and large cell serialization;
- errno 3024, connector timeout, generic error, cursor-close error, and
  `KeyboardInterrupt` release cursor/wrapper once and never expose sentinel;
- monitor receives stable code/type only on error.

### GREEN

Implement incrementally. Do not change list/table success semantics beyond
safe CSV serialization needed for the shared error/size boundary. Delete
obsolete keyword-only validation only after all RED cases pass.

## 11. Task 6 — Close external-tool, harness, task, and sink exception egress

**Files:** `tools/ragflow_tools.py`, `tools/tavily_tools.py`,
`agent/deepagents_harness.py`, `api/research_execution_service.py`,
`api/task_tracker.py`, affected unit tests,
`tests/integration/test_runtime_error_projection.py`, and targeted observation
delivery tests.

### RED

1. Use `DRA_ERROR_EGRESS_SENTINEL` inside a synthetic raw exception, query,
   absolute path, secret-like value, and traceback frame.
2. Drive each affected tool/harness/task path and capture:
   - `caplog` records and `record.exc_info`;
   - returned tool string and a real `ToolMessage` content value;
   - `ExecutionOutcome.error_message` and diagnostics;
   - monitor stream descriptor and retained telemetry record;
   - generic canonical artifact built from the safe result;
   - authenticated REST failure/status/result surface;
   - WebSocket observation/finalization surface.
3. Assert the sentinel and its fragments are absent from serialized forms and
   log args; stable code, normalized exception class, and run/thread/task
   correlation remain.

Expected initial failures include raw RAGFlow/Tavily/MySQL tool text, RAGFlow
retry/cleanup logs, harness `str(exc)`, service outcome message, and task
tracker traceback/message.

### GREEN

- Route affected exception branches through `ErrorProjection`.
- RAGFlow retry logs retain service alias, attempt/max, wait, code, and type;
  cleanup uses fixed `cleanup_failed` with class only.
- Tavily/RAGFlow/MySQL model messages remain useful fixed failure messages.
- Harness messages become fixed per failure kind; call-budget diagnostic fields
  remain unchanged.
- Research service records stable message/code and existing typed diagnostics;
  cancellation uses a fixed message and still re-raises `CancelledError`.
- Task callbacks log task ID, stable event/code, and class without `exc_info` or
  exception formatting. Do not swallow task exceptions or change ordered
  termination semantics.
- Do not alter successful provider/tool content or the existing privacy-safe
  observation projector.

Run targeted tests, then scan only affected runtime paths:

```bash
rg -n 'str\((exc|e)\)|exc_info|logger\.(warning|error|exception).*\{(exc|e)\}' \
  tools/db_connection.py tools/mysql_tools.py tools/ragflow_tools.py \
  tools/tavily_tools.py agent/deepagents_harness.py \
  api/research_execution_service.py api/task_tracker.py
```

Expected: no raw exception egress. Internal exception chaining may remain.

## 12. Task 7 — Reconcile Compose authority and real MySQL negative controls

**Files:** `scripts/mysql_read_only_bootstrap.sh`, `docker-compose.yml`,
`.env.example`, secure-runtime proof/contracts/evidence, bounded lifecycle,
container tests, and their unit tests.

### Compose contract

- `mysql` environment contains only required `MYSQL_ROOT_PASSWORD` and
  `MYSQL_DATABASE`; it must not contain `MYSQL_USER` or `MYSQL_PASSWORD`.
- `mysql-bootstrap` uses `mysql:8.0`, no ports or volumes, app network only,
  `cap_drop: [ALL]`, `no-new-privileges`, `restart: "no"`, and a read-only bind
  of `scripts/mysql_read_only_bootstrap.sh`. Its environment contains root,
  database, user, and password only.
- Backend keeps the parameterized env file but explicitly sets root password
  empty and app user/password/database from required/default interpolations.
- Backend depends on MySQL `service_healthy` and bootstrap
  `service_completed_successfully`.
- Bootstrap depends on MySQL health, validates database/user as
  `[A-Za-z0-9_]{1,64}`, safely SQL-quotes the opaque password, invokes mysql via
  stdin with no secret argv, uses `--batch --skip-column-names --silent`, and
  executes `CREATE USER IF NOT EXISTS`, `ALTER USER`,
  `REVOKE ALL PRIVILEGES, GRANT OPTION`, and exact schema SELECT grant. Shell is
  `set -eu`; no `set -x`.

### RED

- Static/resolved Compose tests prove the three authority environments,
  dependency conditions, security settings, read-only mount, and absence of
  secret values in `docker compose config` output/error.
- Bootstrap unit/static tests prove invalid identifiers stop before mysql,
  hostile password quoting remains data, and script has no stdout/secret log.
- Secure-runtime proof initially fails because its closed service set and
  credential ownership still describe two services/GRANT ALL bootstrap.
- Bounded lifecycle sanitizer rejects any extra service/key/environment,
  bootstrap entrypoint/command drift, port/volume on bootstrap, weaker
  dependency condition, or secret projection.

### GREEN and real lifecycle

1. Implement Compose/script and update the deterministic secure-runtime proof.
   Regenerate secure-runtime JSON/Markdown only via:

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/secure_local_runtime_proof.py build
PYTHON_DOTENV_DISABLED=1 python scripts/secure_local_runtime_proof.py check
```

2. Update `ManagedComposeProject` so `start_mysql()` starts MySQL and completes
   bootstrap before backend; ownership discovery includes the exited one-shot
   container. Sanitization projects credentials as markers only.
3. In the existing single provider-free bounded container lifecycle, before
   the API flow:
   - root creates only task-owned fixture schema/data/procedure or additional
     principal state needed for negative controls;
   - backend/app connection returns `CURRENT_USER()` plus exact sanitized grant
     classification; raw grant text stays inside test assertions;
   - safe SELECT and CTE succeed;
   - scanner rejects multi-statement/comment/delimiter/rename/call/into/file/
     lock/resource cases before execution;
   - direct connector bypass attempts for insert/update/delete/create/drop/
     alter/rename/call and another schema fail;
   - schema/table/row hashes before and after negative controls are identical;
   - 20 sequential queries (pool size 5) succeed;
   - forced generic exception, MySQL 3024 query timeout, and
     cancellation-shaped BaseException all permit subsequent acquisition. The
     timeout fixture uses a task-owned 1,024-row table and a triple cross join
     under `MYSQL_QUERY_TIMEOUT_MS=100`, then verifies errno/classification and
     unchanged task-owned data;
   - row and byte truncation metadata are stable;
   - restart with the same named volume and deliberately broadened task-owned
     app grant proves bootstrap reconverges to exact SELECT-only before backend
     is accepted.
4. Retain the existing provider-free API/restart/idempotency proof and security
   inspection. Never call a provider or mutate a non-task database.
5. Cleanup exact task-owned resources and assert the existing zero-residue
   receipt, now including bootstrap container ownership.

If Docker is unavailable, VM space is insufficient, or a real contract cannot
be made deterministic without additional privilege/dependency, stop and return
the first failed gate. Hosted CI cannot silently replace this release's
required local real-connector proof.

## 13. Task 8 — Update public contracts and prepare immutable v0.1.8 metadata

**Files:** current README/security/docs, changelog, version files,
`docs/releases/v0.1.8.md`, release tests.

### RED

Create `tests/unit/test_v0_1_8_release_metadata.py` first. It must fail because
`0.1.8` identity/note/current links are absent. Freeze SHA-256 of every
historical `docs/releases/v0.1.0.md` through `v0.1.7.md`, and prove v0.1.7 tag
truth is described as immutable/affected rather than rewritten.

### GREEN

- Set `VERSION`, `frontend/package.json`, lock root version, and lock root
  package version to `0.1.8`; do not touch dependency entries.
- Move completed work from `[Unreleased]` to
  `## [0.1.8] - 2026-07-30` without editing earlier changelog sections.
- Create release notes with exact headings:
  `Supported Surface`, `Changes`, `Compatibility And Migration`, `Rollback`,
  `Required Verification`, `Known Limits`.
- Explain:
  - SELECT-only principal/bootstrap/startup attestation;
  - one-statement scanner and query row/byte/time tightening;
  - stable exception projection and sink controls;
  - Connector/Python public pool release;
  - greenlet closure and exact pip diagnostic gate;
  - operators of external MySQL must provision exact SELECT-only grants;
  - existing Compose volume startup reconciles the app principal;
  - `v0.1.7` remains immutable and is affected by the corrected boundaries;
  - rollback means stop recommending v0.1.8 and restore an approved source/
    lock/config tuple; do not move published tags or weaken DB grants;
  - no deployment/provider/hosted/multi-tenant/business impact claim.
- Update `README.md`, `README_CN.md`, `SECURITY.md`, `docs/README.md`, secure
  runtime operations, external services reference, and observation contract.
  Link the new release note as current and retain older links as historical.
- Document `MYSQL_QUERY_TIMEOUT_MS` default/range, exact output budgets,
  Compose three-authority flow, migration steps, validation/troubleshooting,
  and rollback.
- Update existing documentation/release tests instead of duplicating equivalent
  assertions in multiple new files.

## 14. Task 9 — Targeted verification during implementation

Because no approved host `.venv` exists, create one task-owned locked image
tag, for example `dra-v018-test-<random>`, from the current worktree. Record
its image ID and label it with the task Compose project. Run Python tests with
the worktree mounted read-only and task-owned writable tmp/data/output mounts:

```bash
docker build --label <task-label> -f Dockerfile.backend -t <task-image> .
docker run --rm --network none --cap-drop ALL \
  --security-opt no-new-privileges:true \
  -e PYTHON_DOTENV_DISABLED=1 \
  --mount type=bind,src="$PWD",dst=/proof,readonly \
  --tmpfs /tmp:rw,nosuid,nodev,noexec,size=256m \
  --workdir /proof <task-image> \
  python -m pytest -q <targeted tests>
```

The execution window must spell the explicit resolved image/label paths in its
private shell commands; do not persist them in repository files.

Minimum targeted groups:

```bash
python -m pytest -q \
  tests/unit/test_dependency_compatibility.py \
  tests/unit/test_deployment_preflight.py
python -m pytest -q \
  tests/unit/test_error_projection.py \
  tests/unit/test_sql_read_only.py \
  tests/unit/test_db_connection.py \
  tests/unit/test_mysql_tools.py
python -m pytest -q \
  tests/unit/test_ragflow_tools.py \
  tests/unit/test_tavily_tools.py \
  tests/unit/test_deepagents_harness.py \
  tests/unit/test_research_execution_service.py \
  tests/unit/test_task_tracker.py \
  tests/integration/test_runtime_error_projection.py \
  tests/integration/test_observation_delivery.py
python -m pytest -q \
  tests/unit/test_secure_local_container_contracts.py \
  tests/unit/test_bounded_live_producer_lifecycle.py \
  tests/integration/test_secure_local_runtime_proof.py
python -m pytest -q \
  tests/unit/test_release_metadata.py \
  tests/unit/test_v0_1_8_release_metadata.py \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_public_truth_documentation.py \
  tests/unit/test_release_presentation_contracts.py
```

RED evidence must be recorded before production edits for each task. If a RED
test passes unexpectedly, prove it tests the intended behavior before
continuing; do not manufacture a failure.

## 15. Task 10 — Full provider-free candidate verification

Fresh-check HEAD/status before and after. Run from the exact committed local
candidate. The task-owned image and Compose project must be rebuilt from that
commit, not a dirty bind mount.

### Dependency/import and deterministic gates

```bash
python scripts/check_dependency_compatibility.py
python - <<'PY'
import greenlet
import sqlalchemy
import langchain_community
import langchain_classic
print("DRA_RUNTIME_IMPORT_CLOSURE_OK")
PY
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
python scripts/check_canonical_identity.py --root .
python scripts/final_presentation_audit.py --root .
```

Run these inside the exact locked task image except Docker-orchestrating
scripts/tests that require the host Docker socket.

### Full test lanes

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m "not docker"
DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS=true \
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m docker
```

The Docker lane is required locally and in hosted CI. Capture host/VM
preflight, unique project/image identity, real `SHOW GRANTS`, schema/data hash,
pool reuse counts, timeout/truncation metadata, and zero-residue cleanup. Do
not retain secret fixture values in the receipt.

### Frontend and repository checks

```bash
cd frontend
npm ci
npm run test
npm run lint
npm run build
npm audit --audit-level=moderate
cd ..
git diff --check
git status --porcelain=v1 --untracked-files=all
```

Remove only task-owned ignored artifacts such as worktree `frontend/node_modules`
and test caches after verification. Do not remove shared caches or unrelated
worktree files.

### Sensitive and historical identity checks

```bash
git diff --name-only <baseline>...HEAD
git diff --check <baseline>...HEAD
PRIVATE_ROOT='/''Users''/'
PRIVATE_TASK_PREFIX='019''f'
if rg -n "${PRIVATE_ROOT}|${PRIVATE_TASK_PREFIX}[0-9a-f-]{20,}" \
  README.md README_CN.md SECURITY.md CHANGELOG.md docs agent api tools scripts \
  tests .github Dockerfile.backend docker-compose.yml; then
  exit 1
fi
git diff --exit-code <baseline>...HEAD -- \
  docs/releases/v0.1.0.md docs/releases/v0.1.1.md \
  docs/releases/v0.1.2.md docs/releases/v0.1.3.md \
  docs/releases/v0.1.4.md docs/releases/v0.1.5.md \
  docs/releases/v0.1.6.md docs/releases/v0.1.7.md
```

The synthetic marker may exist only in test source as a literal used for
negative controls; refine the scan to prove it is absent from production/docs
and emitted artifacts rather than deleting the test oracle.

## 16. Authority checkpoint before any public action

After all local commits and verification:

1. Confirm branch clean; capture exact HEAD/tree, commit list, full diff, file
   inventory, test commands/results, Docker cleanup receipt, and any skipped
   item.
2. Return the exact receipt through the privately supplied coordination
   channel before declaring the checkpoint complete. Private routing data does
   not enter repository files or commits.
3. Stop. Do not push or create a PR until the independent authority reports the
   findings-only review clean.

The independent authority will run the GStack `review` skill against the actual
`main...HEAD` diff. Findings are evidence to verify, not automatic commands.
For returned findings, read and apply `superpowers:receiving-code-review`,
reproduce each issue, make only same-contract repairs, rerun targeted and full
gates as proportional, and callback with a new exact HEAD/tree. A material
contract change returns to authority; do not improvise.

## 17. Exact-reviewed-head PR publication gate

Only after authority sends a clean publication follow-up:

1. Verify local branch HEAD equals the exact reviewed SHA and status is clean.
2. Verify `origin/main` still equals the reviewed base or rebase only under a
   new authority review. Never publish an unreviewed merge/rebase commit.
3. Push the exact branch without force. Create one non-draft PR to `main`.
4. Required PR structure:
   - result-first Chinese title;
   - `Summary`, `Completion`, `Verification`;
   - `Scope`, `Risk / Impact`, `Compatibility / Migration`, `Rollback`,
     `Documentation impact`, `Non-claims`;
   - actual commands/results only;
   - checkboxes only for pending hosted/merge gates.
5. Read back persisted title, body, base, head ref/OID, draft state, and URL.
   Correct bounded body errors if needed and read back again.
6. Wait for all required hosted checks, including Backend Tests, Secure Local
   Runtime Containers, Frontend Demo Console, and applicable CodeQL/platform
   review. Missing/skipped/cancelled/timed-out is not success.
7. Inspect PR conversation, reviews, and inline threads. Reproduce actionable
   findings. Same-contract repairs return to authority for targeted re-review
   before updating the branch; any new head invalidates prior exact-head
   approval.
8. Immediately before merge, prove:

```bash
test "$(git rev-parse HEAD)" = "$EXACT_REVIEWED_HEAD"
test "$(gh pr view <number> --json headRefOid --jq .headRefOid)" = \
  "$EXACT_REVIEWED_HEAD"
test -z "$(git status --porcelain=v1 --untracked-files=all)"
```

9. Squash merge only when every gate is green. Record merge commit and compare
   `git rev-parse "$MERGE_COMMIT^{tree}"` with the reviewed head tree. Tree
   inequality blocks release.

## 18. v0.1.8 annotated tag and GitHub Release gate

The approved release name is `Decision Research Agent v0.1.8`; tag is
annotated `v0.1.8`. Release body bytes come from the tracked
`docs/releases/v0.1.8.md` at the exact merge commit.

1. Fresh-fetch `main` and exact tag refs. Prove local `main`, `origin/main`, PR
   merge commit, and reviewed tree identity. Ensure no later main commit is
   substituted.
2. Re-run the small release identity/presentation checks from an immutable
   archive of the merge commit. Do not run provider or deployment.
3. Probe local tag, remote tag, and GitHub Release separately. Network/API
   failure is unknown, not absence.
4. If all are absent, create one annotated local tag at the merge commit, push
   the exact tag ref without force, then create a non-draft/non-prerelease
   Release with tracked body.
5. Reconcile partial success idempotently:
   - exact remote tag with no Release: fetch/verify the tag, then create only
     the missing Release;
   - exact Release with exact tag: readback only;
   - any differing tag object/peeled commit/tree/body: stop; never move/delete
     the tag or overwrite public truth without a new decision.
6. Read back and record:
   - annotated tag object type/object ID/tagger/name/message;
   - peeled commit and commit tree;
   - remote exact tag ref;
   - Release tag/name/target/body/draft/prerelease/published URL/time;
   - equality of tracked merge-commit note and persisted Release body;
   - generated source archive HTTP availability and archive top-level identity.
7. Do not attach custom binaries, deploy, sign with an unapproved key, or claim
   provider/hosted/business results.

## 19. Final inventory and cleanup

After release readback:

- fresh-read local `main`, `origin/main`, `v0.1.8`, Release, hosted checks,
  open PRs, local/remote task branch, worktrees, dirty/untracked files, active
  task, Docker resources, and task temporary paths;
- fast-forward the primary DRA `main` only if it is clean, still at the expected
  pre-merge base, and the independent authority confirms no competing owner;
  otherwise leave it untouched and report exact residue;
- delete only the merged task-owned remote branch when retention is not
  required and readback proves the merge/tag retains its tree;
- remove the clean inactive task-owned worktree/branch and prune only stale Git
  worktree metadata;
- remove exact task-owned Docker containers/networks/volumes/image and temporary
  test artifacts; no broad prune;
- verify zero unique commits or dirty changes before cleanup;
- archive the execution task only after it has no further publication or repair
  duty.

If any unique change, competing write owner, open PR, running task, mismatched
tag, or unowned resource prevents safe cleanup, return `DONE_WITH_RESIDUE` with
the exact owner/object and recovery condition.

## 20. Failure and recovery table

| Failure | Stable evidence | Required response |
|---|---|---|
| query scanner uncertainty | `input_invalid` / `unsafe_statement` | reject before pool; add a RED case only if within spec |
| grant mismatch | `privilege_contract_invalid` + class/correlation | no pool/backend readiness; reconcile operator grants |
| bootstrap failure | exited one-shot service, no backend | inspect bounded service state without printing env; fix same-contract script only |
| pool exhaustion after <=5 uses | real connector acquisition failure | reproduce close counts/unread result; do not enlarge pool as a workaround |
| MySQL errno 3024 | `timeout`, configured ms | return fixed metadata; prove cursor/wrapper cleanup |
| byte/row cap | fixed truncation trailer | preserve capped output; do not fetch/serialize unbounded remainder |
| raw sentinel in any sink | failing sink name | stop publication; trace the exact boundary and repair it |
| second `pip check` diagnostic | checker nonzero + bounded parsed count | block build/CI; determine dependency owner; no allowlist expansion without authority |
| Docker unavailable/space low | preflight code and inventory | no broad cleanup/config change; return blocker |
| local/hosted test failure | command + first failure | systematic debugging; no “unrelated/flaky” waiver without proof |
| PR head drift | local/remote OID mismatch | stop; new authority review required |
| hosted check missing/failing | persisted check state | do not merge |
| merge tree mismatch | merge/review tree IDs | do not tag; investigate merge content |
| partial tag/Release | exact persisted object inventory | create only missing matching object; never force/delete |
| final cleanup unsafe | owner + path/ref/resource | preserve and return `DONE_WITH_RESIDUE` |

## 21. Targeted plan-eng-review resolution

This plan was reviewed once for architecture, data flow, security, performance,
failure recovery, test strategy, publication, and scope. User-approved product
direction and terminal authority were not reopened.

### Findings and amendments

| Priority | Finding | Resolution in plan |
|---|---|---|
| P0 | official MySQL image `MYSQL_USER` creates `GRANT ALL` and init scripts do not repair existing volumes | separate one-shot bootstrap, remove app creds from server service, rerun on every start, and require startup grant attestation |
| P0 | stopping an unbuffered fetch early can leave unread rows and poison pooled reuse | application tightens depth-zero LIMIT to 101, drains that bounded result with fetchmany, then closes wrapper publicly |
| P0 | a sync client-side timeout can strand a query/thread/connection | MySQL server owns read-only statement termination via app-inserted MAX_EXECUTION_TIME; connector read timeout remains a response ceiling |
| P0 | raw exception repair limited to monitor would leave logger/model/task/API bypasses | one shared closed projection plus aggregate negative controls across every named sink |
| P1 | `/docker-entrypoint-initdb.d` looked simpler but would not cover retained volumes | rejected in favor of idempotent Compose service and explicit restart convergence proof |
| P1 | wrapping arbitrary SELECT in a derived table could reject duplicate column names or alter semantics | preserve query shape and tighten only the parsed depth-zero numeric LIMIT |
| P1 | SQLAlchemy pin ownership was ambiguous | keep direct requirements unchanged; add greenlet only to exact transitive lock and document LangChain owners |
| P1 | exact-string `pip check` allowlist could be brittle or overly broad | parse one anchored semantic diagnostic, accept clean output, and fail on any second/near-match line |
| P1 | host has no approved pinned Python environment | use task-owned exact-lock backend image; do not create/install a host environment |
| P1 | a separate real-MySQL lifecycle would duplicate expensive setup and cleanup | add negative controls to the existing single bounded provider-free lifecycle while keeping helper contracts testable |
| P2 | a new SQL parser dependency would reduce custom code but expand lock/supply-chain scope | reject; use bounded scanner adequate for the deliberately narrow SELECT contract |

### Performance and scale bounds

- scanner time is linear in a bounded query string;
- server returns at most 101 rows for custom queries;
- client serializes at most 65,536 bytes and keeps only a small batch plus
  output buffer;
- pool size remains 5; the regression runs 20 sequential acquisitions and does
  not manufacture concurrency throughput claims;
- statement execution defaults to 5 seconds and caps at 30 seconds;
- no provider or external paid work is introduced.

### Test architecture

```text
unit RED/GREEN
  ├─ scanner and LIMIT/hint
  ├─ error classifier and hostile __str__
  ├─ grant parser and faithful pooled wrapper
  ├─ fetch/CSV budgets and cleanup
  ├─ pip diagnostic parser
  └─ Compose/sanitizer static contracts
           │
           v
one task-owned real MySQL lifecycle
  ├─ SHOW GRANTS / CURRENT_USER
  ├─ schema/data negative identity
  ├─ SELECT/CTE + row/byte/time caps
  ├─ > pool_size reuse after failures
  ├─ existing-volume grant reconvergence
  └─ exact zero-residue cleanup
           │
           v
full provider-free suite + frontend + identity/presentation
           │
           v
independent findings-only review -> exact-head PR/CI -> merge tree -> tag/Release
```

### Scope fence

This plan changes only the listed safety/runtime/dependency/Compose/docs/release
surface. It explicitly rejects DB framework migration, hosted auth/RBAC,
provider execution, deployment, a generic SQL service, global exception
refactoring, and deferred legacy cleanup.

## 22. Implementation checklist

- [ ] Task 0: mechanically land approved spec/plan and record identities.
- [ ] Task 1: pin greenlet and add exact fail-closed dependency checker.
- [ ] Task 2: add stable error projection with hostile-string tests.
- [ ] Task 3: add one-statement scanner and bounded statement builder.
- [ ] Task 4: add grant attestation and correct connector pool return.
- [ ] Task 5: integrate bounded MySQL fetch/serialization/error/resource paths.
- [ ] Task 6: close RAGFlow/Tavily/harness/task/all-sink exception egress.
- [ ] Task 7: add Compose bootstrap and real MySQL negative/reuse proofs.
- [ ] Task 8: update public contracts and create v0.1.8 release metadata.
- [ ] Task 9: complete every targeted RED→GREEN group.
- [ ] Task 10: complete full local provider-free candidate verification.
- [ ] Authority checkpoint: callback exact local HEAD/tree and stop public work.
- [ ] Findings repair: reproduce, bounded fix, targeted/full reverify, callback.
- [ ] Publication: exact reviewed head push, PR/body readback, hosted gates.
- [ ] Merge: exact PR OID, green checks, squash tree equality.
- [ ] Release: annotated v0.1.8, GitHub Release, body/source identity readback.
- [ ] Cleanup: main/release/PR/ref/worktree/Docker/task inventory to zero residue.

## GSTACK REVIEW REPORT

| Review | Trigger | Runs | Status | Findings |
|---|---|---:|---|---|
| Eng Review | targeted `plan-eng-review` | 1 | CLEAR AFTER AMENDMENTS | Compose existing-volume authority, bounded unread-result handling, server timeout ownership, all-sink projection, dependency owner, Docker environment, and publication recovery were made explicit |
| AutoPlan | not run | 0 | SKIPPED | user required one targeted engineering review and prohibited overlapping controllers |
| CEO/Product Review | not run | 0 | SKIPPED | product direction, included findings, non-goals, and terminal target were already approved |
| Design Review | not run | 0 | SKIPPED | no UI or visual interaction change |

**VERDICT:** ENG CLEARED AFTER AMENDMENTS — the plan has one serial execution
path, explicit authority and failure boundaries, deterministic RED→GREEN and
real-runtime evidence, exact publication identity, and bounded cleanup.

NO UNRESOLVED DECISIONS
