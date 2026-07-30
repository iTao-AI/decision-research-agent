# Decision Research Agent v0.1.8 — Tool Safety and Runtime Closure

Status: Approved bounded design for implementation. Publication is authorized
only after exact-head authority review, required hosted checks, and the
publication gates in the paired implementation plan.

Planning baseline: clean `main@4d1ba5e2d80584e0240abcea4be74fa4ec891eb0`;
current immutable release `v0.1.7`.

## Contract

### 1. Release identity and historical truth

- The next patch identity is `0.1.8` / `v0.1.8`.
- The annotated `v0.1.7` tag, its peeled commit and tree, the tracked
  `docs/releases/v0.1.7.md`, and the published GitHub Release remain unchanged.
- `v0.1.8` is a separate corrective source release. It must describe the
  affected `v0.1.7` boundaries without claiming that earlier history was
  clean, rewritten, or retroactively repaired.
- The repository and container configuration remain the supported artifact.
  This release does not add a Python wheel, hosted service, deployment, or
  live-provider acceptance claim.

### 2. MySQL statement admission

- The model-facing custom-query tool accepts exactly one read-only MySQL
  statement whose governing operation is `SELECT`; a `WITH` or `WITH
  RECURSIVE` prefix is accepted only when its depth-zero governing statement is
  `SELECT`.
- One optional terminal semicolon is compatible. A second statement, a
  non-terminal semicolon, delimiter directive, unbalanced quote or parenthesis,
  or comment outside a quoted literal is rejected before a database connection
  is acquired.
- The scanner treats quoted strings and quoted identifiers as data, so a safe
  query is not rejected merely because a literal contains a semicolon or a
  blocked keyword.
- DML, DDL, DCL, transaction/session control, stored-program execution,
  dynamic SQL, file access, locking reads, advisory-lock functions, and
  resource-amplification functions are rejected fail closed. This includes at
  least `INTO`, `OUTFILE`, `DUMPFILE`, `CALL`, `DO`, `HANDLER`, `LOAD`,
  `PREPARE`, `EXECUTE`, `DEALLOCATE`, `SET`, `USE`, `FOR UPDATE`, `FOR SHARE`,
  `LOCK IN SHARE MODE`, `SLEEP`, `BENCHMARK`, `GET_LOCK`, `RELEASE_LOCK`,
  `IS_FREE_LOCK`, `IS_USED_LOCK`, `LOAD_FILE`, `MASTER_POS_WAIT`, and
  `SOURCE_POS_WAIT` when they occur as SQL tokens rather than literal content.
- Scanner uncertainty is rejection, not pass-through. Rejection returns a
  stable code and fixed message and never echoes the query.
- Safe ordinary `SELECT`, `UNION`, `WITH`, and `WITH RECURSIVE` queries remain
  compatible within the result budgets below.

### 3. Database authority and credential separation

- The backend's MySQL principal is an application read-only principal. It has
  exactly schema-scoped `SELECT` on the configured application database plus
  the unavoidable `USAGE` grant; it has no global `SELECT`, write/DDL/DCL
  privilege, grant option, role grant, privilege on another schema, or root
  credential.
- Local Compose has three distinct authorities:
  1. the `mysql` service owns only server bootstrap root authority and the
     database name;
  2. a one-shot `mysql-bootstrap` service owns the root and application
     credentials only long enough to reconcile the application principal;
  3. the `backend` service owns only the application principal and receives an
     explicit empty root credential.
- The one-shot bootstrap runs on first and subsequent starts, including an
  existing named volume. It creates or reconciles the configured application
  principal, removes direct privileges and grant option, and grants only
  schema-scoped `SELECT`. It does not mutate application tables or rows.
- The bootstrap validates identifier-shaped database/user inputs, treats the
  password as opaque data, passes secrets without command-line or log egress,
  and exits nonzero on any failed statement. Backend startup waits for both
  MySQL health and successful bootstrap completion.
- Before constructing the connection pool, application code opens one bounded
  preflight connection, reads `CURRENT_USER()` and `SHOW GRANTS FOR
  CURRENT_USER()`, and accepts only the exact grant set above. Missing,
  additional, malformed, or unreadable grants fail closed with
  `privilege_contract_invalid`; raw principal or grant text is not emitted.
- The application check applies to Compose and external MySQL alike. An
  external operator may provision credentials differently, but the observed
  grants must satisfy the same contract.

### 4. Stable error projection

- External-service tools, MySQL connection/tool paths, the framework-harness
  boundary, tracked-task callbacks, and run execution expose errors through a
  project-owned stable projection: allowlisted code, bounded fixed message,
  exception class name, and available correlation identifiers.
- Supported runtime codes are a closed set that includes
  `configuration_missing`, `input_invalid`, `unsafe_statement`, `timeout`,
  `service_unavailable`, `resource_not_found`, `privilege_contract_invalid`,
  `pool_exhausted`, `cleanup_failed`, and `execution_failed`.
- Logger records may include the stable code, exception class, attempt count,
  service/tool alias, and task/run/thread correlation ID. They must not include
  `str(exc)`, exception args, `exc_info`, traceback, query text, input payload,
  filesystem path, URL containing credentials, provider response, or secret
  marker.
- Model-visible `ToolMessage` content and `ExecutionOutcome.error_message` use
  fixed allowlisted messages. Original exceptions remain chained internally so
  class-level diagnosis is available to code and tests, but raw messages do
  not cross the boundary.
- The same negative boundary applies to logger, model context, monitor events,
  retained telemetry, canonical artifacts, REST responses, and WebSocket
  events. A synthetic exception marker containing query/path/traceback/secret
  text must be absent from every sink while the stable code, exception class,
  and relevant correlation identity remain observable.
- Successful substantive tool results remain content authority. This contract
  narrows exception egress; it does not replace Evidence, artifact, or terminal
  result authority.

### 5. Dependency closure

- `SQLAlchemy==2.0.51` remains transitive runtime surface owned by the pinned
  `langchain-community==0.4.2` and `langchain-classic==1.0.8` distributions.
- Because SQLAlchemy 2.0.51 declares `greenlet>=1` on the supported Linux
  architectures, the no-deps release lock adds exactly one transitive runtime
  closure pin: `greenlet==3.5.4` in `constraints.txt`. It is not promoted to a
  direct product requirement and adds no framework.
- The pin must import on Python 3.11 and have supported Linux container wheels;
  the Docker/CI platform proof is authoritative for the release.
- A repository-owned compatibility check runs `python -m pip check` and accepts
  only either a clean result or the single already documented diagnostic that
  `ragflow-sdk==0.13.0` requires pytest below 9 while the deliberate lock pins
  `pytest==9.0.3`. Missing packages, wrong versions, malformed output, or any
  second diagnostic fail closed.
- The compatibility check runs after the exact no-deps install in both backend
  and container CI jobs and while building the backend image. A successful
  import proof covers `greenlet`, `sqlalchemy`, `langchain_community`, and
  `langchain_classic`.
- No prior release note or `v0.1.7` metadata is edited to imply a conflict-free
  dependency graph.

### 6. Connector pool lifecycle

- The pinned `mysql-connector-python==9.7.0` contract is authoritative:
  releasing a `PooledMySQLConnection` calls its public `close()` exactly once,
  which resets and returns the underlying connection to its pool.
- Application code never passes a pooled wrapper to
  `MySQLConnectionPool.add_connection()` and never uses private connector
  internals to simulate release.
- Success, connector error, validation-independent execution error,
  `BaseException`/cancellation, cursor cleanup error, and timeout all attempt
  cursor closure followed by pooled-wrapper closure exactly once. Cleanup
  failures use stable error projection and do not mask an already active
  exception.
- Unit tests use a contract-faithful fake rather than `MagicMock` expectations
  that invent an SDK lifecycle. Required real-connector proof performs more
  sequential acquisitions than the pool size and proves reuse after success,
  exception, timeout, and cancellation-shaped exits.

### 7. Custom-query budgets

- Each admitted custom query receives these release constants:
  - `max_rows = 100`;
  - `fetch_batch_rows = 25`;
  - `max_serialized_bytes = 65_536`, including header and truncation metadata;
  - `max_execution_ms = 5_000` by default, configurable only through
    `MYSQL_QUERY_TIMEOUT_MS` in the inclusive range `100..30_000`.
- Application-owned SQL adds a MySQL `MAX_EXECUTION_TIME` optimizer hint to the
  governing read-only `SELECT`. It also appends or tightens a numeric
  depth-zero `LIMIT` to at most `max_rows + 1`; ambiguous/non-numeric top-level
  limit syntax is rejected. User-owned optimizer comments are not accepted.
- Rows are read with unbuffered, bounded `fetchmany(fetch_batch_rows)` calls.
  At most `max_rows + 1` server rows are consumed, sufficient to prove row
  truncation and fully drain the bounded result before pool return.
- CSV serialization uses the standard library, UTF-8 byte accounting, and a
  fixed metadata trailer. Output never exceeds `max_serialized_bytes`. The
  trailer has stable `code=result_truncated`, reason
  `row_limit|byte_limit|row_and_byte_limit`, returned-row count, and configured
  limits.
- MySQL timeout errno `3024` and connector timeout classes map to a stable
  `timeout` result containing `max_execution_ms`; raw server messages are not
  returned. A monotonic elapsed observation may classify a late response as
  timeout but never weakens the server hint or connector response ceiling.
- Ordinary non-truncated CSV results and empty-result wording remain compatible.
  Queries relying on more than 100 rows, more than 65,536 serialized bytes,
  comments, ambiguous limits, or more than the configured statement budget are
  intentionally tightened in `v0.1.8`.

## Non-goals

- No Git history rewrite, force-moved/deleted `v0.1.7`, provider/user-held
  credential rotation, provider-account action, deploy, paid provider
  execution, remote tracing, or real business-database mutation. The local
  bootstrap may only reconcile the task/operator-supplied application
  principal described by this contract; it does not derive or persist a new
  credential value.
- No DB-layer rewrite, ORM migration, new SQL parser dependency, hosted or
  multi-tenant RBAC, scheduler, MCP, GBrain, EvalOps platform, autonomous
  repair, or unrelated Agent feature.
- No attempt to make a SELECT scanner the sole security boundary; lexical
  admission and a database-enforced least-privilege principal are both
  required.
- No universal SQL-dialect support, stored program support, mutation API,
  unlimited result streaming, hard end-to-end network deadline, or
  exactly-once external effect claim.
- No cleanup-only refactor, historical compatibility-layer deletion, or broad
  raw-exception rewrite outside the affected tool/harness/task boundary.
- No resolution of the documented RAGFlow/pytest metadata conflict in this
  patch.

## Acceptance

### Statement and authority proof

- Provider-free unit tests prove one-statement parsing across quoted literals,
  safe `SELECT`/`UNION`/CTE cases, comments, delimiters, unbalanced syntax,
  write/DDL/DCL/session/stored-program/file/lock/resource constructs, and
  top-level limit rewriting.
- A task-owned real MySQL 8.0 Compose lifecycle proves:
  - resolved credential authority separation;
  - exact `CURRENT_USER()` and `SHOW GRANTS` acceptance;
  - safe SELECT and CTE compatibility;
  - negative statements cannot change schema/data identity;
  - direct insert/update/delete/create/drop/rename/call/file/global access fail
    under the application principal even if lexical admission is bypassed;
  - restart against the same task-owned volume re-runs the bootstrap and
    restores exact read-only grants;
  - every task-owned container, volume, network, image, and temporary path is
    inventoried and cleaned without broad prune.

### Error, lifecycle, and budget proof

- One synthetic exception marker is absent from logger, ToolMessage/model
  context, monitor, telemetry, canonical artifact, REST, and WebSocket sinks;
  expected stable code/class/correlation data is present.
- Contract-faithful unit tests and real Connector/Python 9.7.0 tests prove
  public `close()` return semantics, more than pool-size reuse, and release on
  success/error/timeout/cancellation-shaped paths.
- Custom-query tests prove row, serialized-byte, and server statement budgets;
  deterministic truncation/timeout metadata; bounded `fetchmany`; and
  cursor/connection release in all terminal paths.

### Dependency, documentation, and release proof

- Linux/Docker exact-lock installation passes the repository compatibility
  checker with no diagnostic beyond the single approved RAGFlow line, and the
  four required imports succeed.
- Backend/container CI run the compatibility checker; any second `pip check`
  diagnostic fails a test and the job.
- Current reference docs, secure local operations, `.env.example`, README
  surfaces, changelog, Superpowers index, and `docs/releases/v0.1.8.md` describe
  the tightened contract, operator migration, rollback, verification, and
  non-claims. Historical release notes remain byte-identical.
- Version identity is exactly `0.1.8` in `VERSION`, frontend package metadata,
  and lockfile root. A dedicated v0.1.8 metadata contract freezes all earlier
  release-note hashes including v0.1.7.
- Required provider-free proofs, the full non-Docker suite, the required Docker
  lane, frontend test/lint/build/audit, canonical identity, presentation audit,
  diff checks, and sensitive-marker scans pass from the exact reviewed head.
- PR title/body, hosted CI and platform review are read back from GitHub. Merge
  occurs only if the PR head still equals the reviewed head and all required
  checks succeed. The squash-merge tree equals the reviewed head tree.
- An annotated `v0.1.8` tag and non-draft/non-prerelease GitHub Release are
  created only from that merge commit. Tag object, peeled commit, tree, Release
  body, target, generated source archives, final `main`/`origin/main`, open PRs,
  branches, worktrees, and task residue are read back before closeout.
