# Secure Local Runtime v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the supported source and local-Compose runtime secure by default
while preserving the credential-free loopback Console, authenticated Tool
Client, and every existing business contract.

**Architecture:** Add one frozen application-owned runtime access policy that
is loaded once when the FastAPI application is constructed. HTTP and WebSocket
transport adapters project peer, authority, forwarding, Origin, and credential
context into that policy before existing routes run. Deliver the capability in
three ordered pull requests: runtime access/protocol, container delivery/proof,
then pure `v0.1.5` release metadata.

**Tech Stack:** Python 3.11, FastAPI 0.138, Starlette 1.3, Pydantic 2.13,
Uvicorn 0.49, pytest 9, Docker Compose, MySQL 8, GitHub Actions, React/Vitest
regression checks, Python standard-library `hmac`, `ipaddress`, `urllib`, JSON,
and filesystem primitives.

## Global Constraints

- Implement only
  `docs/superpowers/specs/2026-07-18-secure-local-runtime-design.md`.
- Begin from the clean spec branch containing the approved design and this
  implementation plan. Keep `VERSION` at `0.1.4` throughout PR A and PR B.
- Deliver exactly three ordered changes: PR A runtime access/protocol; PR B
  container delivery/proof rebased onto PR A; PR C pure `v0.1.5`
  release-preparation metadata after PR A and PR B merge.
- Use TDD for every behavior change: focused RED, minimal implementation,
  focused GREEN, then the broader matrix named by the task.
- `API_SECRET` is loaded once per application construction. Runtime mutation
  of the environment is unsupported; tests replace the frozen app-state policy
  explicitly instead of adding a `testclient` production exception.
- Preserve public `GET /health`, `/docs`, `/openapi.json`, `/redoc`, and CORS
  preflight access. Every other general HTTP route uses the approved access
  policy; review and Evidence-verification routes retain their feature-owned
  gates.
- Preserve `X-API-Key`, `DECISION_RESEARCH_AGENT_API_KEY`, Tool Client request
  and result behavior, Console loopback behavior, run/result/Evidence schemas,
  database schemas, framework authority, and downstream fixtures.
- Remove WebSocket `?api_key=` completely. Do not add a compatibility flag,
  browser credential storage, cookie/session auth, bearer/OIDC, TLS, proxy
  trust, hosted mode, rate limits, RBAC, or multi-user behavior.
- Set supported source and container Uvicorn launchers to warning-level logging
  so the locked transport does not emit a rejected query credential at info
  level. Do not add a project-owned Uvicorn logging filter or claim that an
  operator-enabled verbose server log is sanitized.
- PR A must change the `.env.example` `API_SECRET` line to empty in the same
  commit series that rejects `your-secret-key`. PR B owns all remaining
  provider, tracing, and database template hardening.
- PR B keeps the backend image UID unchanged. Add `cap_drop: [ALL]` and
  `no-new-privileges:true`, but do not add `USER`, `read_only`, broad `chown`,
  or a volume-format/ownership migration.
- The normal backend CI job owns only non-Docker tests. One required container
  job owns every `pytest.mark.docker` case with
  `DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS=true`; do not run Docker-marked
  tests in both jobs.
- Deterministic evidence is credential-free, path-free, provider-free, and
  commit-SHA-free. It proves production adapters and declared container
  contracts; the Docker lane and post-release archive smoke remain separate
  runtime evidence.
- Do not add dependencies, migrations, Agent middleware, LangGraph checkpoint
  authority, LangSmith access authority, or a public runtime-mode enum.
- Do not push, create or update a PR, merge, tag, publish a release, deploy, or
  clean a worktree without the separate authorization applicable to that
  action.
- Public text must remain English, provider-neutral, consumer-neutral, and free
  of private paths, private project names, credentials, or development-process
  motivation.

---

## File And Responsibility Map

### PR A — Runtime access and protocol boundary

| File | Responsibility |
|---|---|
| `api/runtime_access.py` | Frozen policy/context/decision contracts, strict secret normalization, peer/authority/forwarding classification, UTF-8 byte comparison, HTTP/WS context adapters |
| `api/cors_config.py` | Strict singular Origin parser, normalized CORS configuration, empty-secret/loopback cross-field validation |
| `api/server.py` | App-state policy wiring, general HTTP middleware, bounded errors, ordered WebSocket handshake, warning-level source launcher, once-only startup warning |
| `api/review_api.py` | Reuse byte-oriented secret comparison while retaining the review-owned feature gate and error contract |
| `api/evidence_verification_api.py` | Reuse byte-oriented secret comparison while retaining verification-owned authority and errors |
| `.env.example` | PR A changes only the `API_SECRET` comment/value to the supported empty source-loopback template |
| `tests/conftest.py` | Explicit authenticated app-state policy fixture for existing general API integration tests |
| `tests/unit/test_runtime_access.py` | Pure strict policy, normalization, launcher, and transport-context contracts |
| `tests/unit/test_auth_middleware.py` | Production middleware status/error/order and once-only warning contracts |
| `tests/unit/test_cors_config.py` | Origin grammar, normalization, cross-field, methods/headers/credentials contracts |
| `tests/integration/test_runtime_access_protocol.py` | Real FastAPI middleware and WebSocket handshake matrix, including no lookup before access |
| existing API/proof tests | Replace environment-mutation assumptions with explicit frozen policy setup; preserve all business behavior |
| API/architecture/getting-started/Console/security docs | Public supported modes, migration, rollback, error codes, and non-claims for PR A only |

### PR B — Container delivery and security proof

| File | Responsibility |
|---|---|
| `.env.example` | Empty provider/database secret values, tracing off, application MySQL user |
| `docker-compose.yml` | Loopback host publication, required interpolation, health/startup ordering, capability reduction |
| `Dockerfile.backend` | Exact stdlib `/health` image check plus warning-level Uvicorn while retaining container-internal `0.0.0.0` |
| `.dockerignore` | Narrow build context while preserving required source and durable-HITL evidence |
| `tests/unit/test_secure_local_container_contracts.py` | Static Compose, Dockerfile, env-template, build-context, and negative configuration contracts |
| existing container helpers/tests | Real health, runtime inspect, volume write/restart, no-provider, bounded cleanup |
| `.github/workflows/ci.yml` | Disjoint required non-Docker and Docker test jobs plus deterministic proof gate |
| `scripts/secure_local_runtime_contracts.py` | Exact 16-case report schema/order/observations, serializers, public boundaries and limits |
| `scripts/secure_local_runtime_proof.py` | Production-path case builder and bounded `build`/`check` CLI |
| proof unit/integration tests | Strict report, production mutation, CLI, bounded read/write, byte stability, public safety |
| `docs/evidence/secure-local-runtime-v1.json` | Committed canonical deterministic JSON evidence |
| `docs/evidence/secure-local-runtime-v1.md` | Committed canonical deterministic Markdown evidence |
| `docs/operations/secure-local-runtime.md` | Supported source/Compose operations, secret setup, verification, rollback, residual limits |
| shared README/docs/CHANGELOG files | Final discoverability and exact `Unreleased` capability record after rebasing PR A |

### PR C — `v0.1.5` release preparation

| File | Responsibility |
|---|---|
| `VERSION`, frontend package and lock | Exact `0.1.5` identity; lock semantics unchanged apart from two version fields |
| `CHANGELOG.md` | Empty `Unreleased`, archive the exact PR A + PR B capability under `0.1.5` |
| `SECURITY.md` | Current-version supported local runtime boundary |
| `docs/releases/v0.1.5.md` | Supported surface, migration, rollback, verification, limitations, non-claims |
| README/docs indexes | Discover the current release without rewriting historical releases |
| release metadata tests | Version, ordering, history, discovery, lockfile, and honest publication boundaries |

## Ordering, Isolation, And Parallel Work

1. PR A Tasks 1–5 are serial at their shared access/configuration boundary.
2. A separate isolated container lane may execute the static portions of Tasks
   6–7 in parallel with PR A only if it owns exclusively `Dockerfile.backend`,
   `docker-compose.yml`, `.dockerignore`, and container-specific tests. It must
   not modify `.env.example`, CI, proof, README/docs indexes, `CHANGELOG.md`, or
   any `api/**` file.
3. The parent integrates the container lane only after PR A is reviewed and
   landed. PR B then rebases onto the exact merged PR A tree before it completes
   `.env.example`, CI, proof, and shared documentation.
4. PR A and PR B never share an index or write concurrently in one worktree.
   Child lanes return one clean bounded commit; the parent owns integration,
   conflicts, the final diff, and full verification.
5. Stop after each feature branch is locally clean and verified. Push/PR/merge
   are separate actions. Do not begin PR C until `origin/main` contains both
   reviewed feature trees.

---

## PR A — Runtime Access And Protocol Boundary

### Task 1: Define The Frozen Runtime Access Policy

**Files:**

- Create: `api/runtime_access.py`
- Create: `tests/unit/test_runtime_access.py`

**Interfaces:**

- Produces: `RuntimeAccessConfigurationError`, `RuntimeAccessPolicy`,
  `RequestAccessContext`, `AccessDecision`, `normalize_api_secret`,
  `load_runtime_access_policy`, `credentials_match`,
  `decide_runtime_access`, `build_http_access_context`, and
  `build_websocket_access_context`.
- Consumes: one process environment snapshot and Starlette request/WebSocket
  metadata only. It does not inspect routes, databases, run state, or framework
  state.

- [ ] **Step 1: Write the strict RED contract tests**

Create parameterized tests covering:

```python
@pytest.mark.parametrize(
    ("raw", "expected"),
    [(None, None), ("", None), ("real-secret", "real-secret"), ("密钥", "密钥")],
)
def test_normalizes_supported_secret_values(raw, expected):
    policy = load_runtime_access_policy({} if raw is None else {"API_SECRET": raw})
    assert policy.secret_value == expected

@pytest.mark.parametrize("raw", ["your-secret-key", " ", "\t\n"])
def test_rejects_legacy_or_whitespace_only_secret(raw):
    with pytest.raises(
        RuntimeAccessConfigurationError,
        match="runtime_access_configuration_invalid",
    ):
        load_runtime_access_policy({"API_SECRET": raw})

def test_utf8_credentials_compare_without_type_error():
    assert credentials_match("密钥", "密钥") is True
    assert credentials_match("错误", "密钥") is False
    assert credentials_match(None, "密钥") is False
```

Freeze exact access decisions for:

```python
RequestAccessContext(
    transport="http",
    direct_peer="127.0.0.1",
    authority_host="127.0.0.1:8000",
    origin=None,
    forwarded_headers_present=False,
    header_credential=None,
    query_credential_present=False,
)
```

and the IPv6/IPv4-mapped, remote, missing/malformed peer, unsafe/malformed or
duplicate Host, forwarding-present, configured-key, invalid Origin, and
WebSocket-query variants. Assert frozen instances reject field mutation and
constructors reject unexpected fields or non-boolean values.

- [ ] **Step 2: Run Task 1 RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_runtime_access.py -q
```

Expected: collection fails with `ModuleNotFoundError: api.runtime_access`.

- [ ] **Step 3: Implement the minimal strict contracts and decision order**

Use strict frozen Pydantic models and these exact public-internal signatures:

```python
AccessDecisionCode = Literal[
    "allowed_loopback",
    "allowed_api_key",
    "api_auth_not_configured",
    "api_key_invalid",
    "local_authority_required",
    "forwarded_request_rejected",
    "origin_not_allowed",
    "query_credential_rejected",
]

class RuntimeAccessConfigurationError(RuntimeError):
    """Bounded startup failure for an invalid runtime access configuration."""

class RuntimeAccessPolicy(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    api_secret: SecretStr | None
    allow_unauthenticated_loopback: bool = True

    @property
    def secret_value(self) -> str | None:
        return (
            None
            if self.api_secret is None
            else self.api_secret.get_secret_value()
        )

class RequestAccessContext(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    transport: Literal["http", "websocket"]
    direct_peer: str | None
    authority_host: str | None
    origin: str | None
    forwarded_headers_present: bool
    header_credential: str | None
    query_credential_present: bool

class AccessDecision(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    allowed: bool
    code: AccessDecisionCode

def normalize_api_secret(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    if value == "your-secret-key" or value.isspace():
        raise RuntimeAccessConfigurationError(
            "runtime_access_configuration_invalid"
        )
    return value

def load_runtime_access_policy(
    environ: Mapping[str, str] | None = None,
) -> RuntimeAccessPolicy:
    source = os.environ if environ is None else environ
    value = normalize_api_secret(source.get("API_SECRET"))
    return RuntimeAccessPolicy(
        api_secret=None if value is None else SecretStr(value),
    )

def credentials_match(supplied: str | None, configured: str) -> bool:
    return hmac.compare_digest(
        (supplied or "").encode("utf-8"),
        configured.encode("utf-8"),
    )

def decide_runtime_access(
    policy: RuntimeAccessPolicy,
    context: RequestAccessContext,
    *,
    allowed_origin: str | None,
) -> AccessDecision:
    if context.transport == "websocket" and context.query_credential_present:
        return AccessDecision(
            allowed=False,
            code="query_credential_rejected",
        )
    if context.origin is not None and context.origin != allowed_origin:
        return AccessDecision(allowed=False, code="origin_not_allowed")
    if policy.secret_value is not None:
        matched = credentials_match(
            context.header_credential,
            policy.secret_value,
        )
        return AccessDecision(
            allowed=matched,
            code="allowed_api_key" if matched else "api_key_invalid",
        )
    if not policy.allow_unauthenticated_loopback:
        return AccessDecision(
            allowed=False,
            code="api_auth_not_configured",
        )
    if context.forwarded_headers_present:
        return AccessDecision(
            allowed=False,
            code="forwarded_request_rejected",
        )
    if not direct_peer_is_loopback(context.direct_peer):
        return AccessDecision(
            allowed=False,
            code="api_auth_not_configured",
        )
    if not authority_is_explicit_loopback(context.authority_host):
        return AccessDecision(
            allowed=False,
            code="local_authority_required",
        )
    return AccessDecision(allowed=True, code="allowed_loopback")
```

Decision order is exact:

1. WebSocket `api_key` query presence -> `query_credential_rejected`.
2. Present Origin not exactly equal to the one configured Origin ->
   `origin_not_allowed`.
3. Configured secret -> byte comparison; correct key allows every direct peer,
   missing/wrong key -> `api_key_invalid`.
4. Empty secret + any forwarding identity header ->
   `forwarded_request_rejected`.
5. Empty secret + absent/malformed/non-loopback direct peer ->
   `api_auth_not_configured`.
6. Empty secret + authority other than exact `127.0.0.1` or `[::1]`, with an
   optional valid port -> `local_authority_required`.
7. Otherwise -> `allowed_loopback`.

Use `ipaddress.ip_address`; normalize `IPv6Address.ipv4_mapped` before the peer
loopback test. Parse authority structurally, reject userinfo, invalid ports,
paths, queries, fragments, DNS names, `localhost`, and duplicate/missing Host.
Detect forwarding header *presence*, including empty values, for this fixed
case-insensitive set:

```python
FORWARDED_IDENTITY_HEADERS = frozenset({
    "forwarded",
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
    "x-forwarded-port",
    "x-real-ip",
    "true-client-ip",
    "cf-connecting-ip",
})
```

The HTTP and WebSocket context builders inspect raw ASGI headers. They extract
one Host, at most one `X-API-Key`, and at most one Origin. A missing or duplicate
Host becomes `authority_host=None`; duplicate credentials become
`header_credential=None`; duplicate Origin becomes a bounded invalid-present
value that can only produce `origin_not_allowed`. They copy only these bounded
selected fields and never preserve a raw URL, query string, or complete header
map.

- [ ] **Step 4: Run Task 1 GREEN**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_runtime_access.py -q
```

Expected: all pure policy, parsing, immutability, and UTF-8 cases pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add api/runtime_access.py tests/unit/test_runtime_access.py
git commit -m "feat(api): define runtime access policy"
```

---

### Task 2: Make CORS A Strict Browser Boundary

**Files:**

- Modify: `api/cors_config.py`
- Modify: `tests/unit/test_cors_config.py`
- Modify: `tests/unit/test_regression.py`

**Interfaces:**

- Consumes: a frozen `RuntimeAccessPolicy` and the singular
  `DECISION_RESEARCH_AGENT_CORS_ALLOWED_ORIGIN` environment value.
- Produces: frozen `CorsConfiguration`, `load_cors_configuration`, existing
  `get_allowed_origins`, and existing `validate_cors_origin` compatibility
  helpers.

- [ ] **Step 1: Write the CORS grammar and cross-field RED matrix**

Require no origin by default, normalization of a single trailing slash, and
exact rejection of invalid values:

```python
@pytest.mark.parametrize(
    "origin",
    [
        "*", "null", " ", "https://a.example,https://b.example",
        "ftp://example.com", "https://user@example.com",
        "https://example.com/path", "https://example.com?query=1",
        "https://example.com#fragment", "https://*.example.com",
        "https://example.com:invalid",
    ],
)
def test_rejects_non_origin_values(origin):
    with pytest.raises(CorsConfigurationError, match="cors_origin_invalid"):
        load_cors_configuration(
            access_policy=load_runtime_access_policy(
                {"API_SECRET": "configured"}
            ),
            environ={CORS_ALLOWED_ORIGIN_ENV: origin},
        )

def test_empty_secret_rejects_remote_browser_origin():
    with pytest.raises(
        CorsConfigurationError,
        match="cors_origin_requires_authenticated_runtime",
    ):
        load_cors_configuration(
            access_policy=load_runtime_access_policy({}),
            environ={CORS_ALLOWED_ORIGIN_ENV: "https://example.com"},
        )
```

Also prove empty secret accepts only literal `http://127.0.0.1:5173` or
`http://[::1]:5173`, not `localhost`; configured secret accepts one exact
HTTP/HTTPS origin; `allow_credentials` is false; methods are exactly
`GET, POST, OPTIONS`; headers are exactly `Content-Type, Idempotency-Key,
X-API-Key`.

- [ ] **Step 2: Run Task 2 RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_cors_config.py \
  tests/unit/test_regression.py -q
```

Expected: current permissive string passthrough accepts invalid origins and no
cross-field configuration type exists.

- [ ] **Step 3: Implement exact Origin normalization**

Use these interfaces and constants:

```python
CORS_ALLOWED_ORIGIN_ENV = "DECISION_RESEARCH_AGENT_CORS_ALLOWED_ORIGIN"
CORS_ALLOWED_METHODS = ("GET", "POST", "OPTIONS")
CORS_ALLOWED_HEADERS = ("Content-Type", "Idempotency-Key", "X-API-Key")

class CorsConfigurationError(RuntimeError):
    """Bounded startup failure for an invalid browser Origin configuration."""

class CorsConfiguration(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    allowed_origin: str | None
    allow_credentials: bool = False
    allow_methods: tuple[str, ...] = CORS_ALLOWED_METHODS
    allow_headers: tuple[str, ...] = CORS_ALLOWED_HEADERS

    @property
    def allowed_origins(self) -> list[str]:
        return [] if self.allowed_origin is None else [self.allowed_origin]

```

Keep the exact loader interface
`load_cors_configuration(*, access_policy: RuntimeAccessPolicy, environ:
Mapping[str, str] | None = None) -> CorsConfiguration`.

Parse with `urllib.parse.urlsplit`. Require scheme `http`/`https`, hostname,
valid optional port, no username/password/query/fragment, and path only empty
or `/`. Reconstruct the normalized exact origin without a trailing slash. For
empty-secret mode, parse the hostname as an IP literal and require exact
`127.0.0.1` or `::1`.

Compatibility helpers delegate to the same parser; they must not reintroduce
the retired `FRONTEND_ORIGIN` alias or wildcard behavior.

- [ ] **Step 4: Run Task 2 GREEN**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_cors_config.py \
  tests/unit/test_regression.py -q
```

Expected: exact grammar, cross-field, and compatibility tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add api/cors_config.py tests/unit/test_cors_config.py \
  tests/unit/test_regression.py
git commit -m "feat(api): validate local browser origin"
```

---

### Task 3: Enforce The HTTP Access Boundary At Application Construction

**Files:**

- Modify: `api/server.py`
- Modify: `api/review_api.py`
- Modify: `api/evidence_verification_api.py`
- Modify: `.env.example`
- Modify: `tests/conftest.py`
- Modify: `tests/unit/test_auth_middleware.py`
- Modify: `tests/unit/test_health_endpoint.py`
- Create: `tests/integration/test_runtime_access_protocol.py`

**Interfaces:**

- Consumes: Task 1 `RuntimeAccessPolicy` and Task 2 `CorsConfiguration`.
- Produces: app-state `runtime_access_policy` and `cors_configuration`,
  `RuntimeAccessMiddleware`, bounded HTTP error projection, and an explicit
  authenticated test fixture.
- Preserves: public-path bypass and independent review/verification feature
  gates.

- [ ] **Step 1: Write the middleware and bootstrap RED tests**

Build a minimal FastAPI app with the production middleware and explicit
Starlette peer identity:

```python
def client_for(app, *, peer="127.0.0.1", base_url="http://127.0.0.1"):
    return TestClient(
        app,
        base_url=base_url,
        client=(peer, 50000),
        follow_redirects=False,
    )
```

Freeze this matrix through a real protected route:

- empty secret + explicit IPv4/IPv6 loopback peer/Host -> route response;
- empty secret + remote/missing peer -> `503 api_auth_not_configured`;
- empty secret + `Host: localhost`/remote/malformed/duplicate ->
  `503 local_authority_required`;
- empty secret + any approved forwarding-header name, including empty value ->
  `503 forwarded_request_rejected`;
- configured secret + missing/wrong key -> `401 api_key_invalid`;
- configured secret + correct UTF-8 key for local and remote peer -> route;
- present disallowed Origin -> `403 origin_not_allowed` before route;
- `/health`, docs, OpenAPI, Redoc, and OPTIONS bypass general authentication;
- review and Evidence-verification paths reach their existing feature-owned
  `404/401/503` responses rather than a general runtime error;
- repeated empty-secret requests produce no per-request warning.

Require top-level Tool-Client-compatible errors:

```python
assert response.json() == {
    "code": "api_key_invalid",
    "problem": "The service credential is invalid.",
    "cause": "X-API-Key did not match the configured service credential.",
    "fix": "Provide the configured X-API-Key.",
    "retryable": False,
}
```

Use stable equivalent text for the three `503` codes and `origin_not_allowed`;
never include peer, Host, Origin, header value, secret length, or raw URL.

- [ ] **Step 2: Run Task 3 RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_auth_middleware.py \
  tests/unit/test_health_endpoint.py \
  tests/integration/test_runtime_access_protocol.py -q
```

Expected: remote empty-secret requests are accepted, errors use the legacy
`detail` response, CORS is permissive, and app state has no frozen policy.

- [ ] **Step 3: Wire one immutable process configuration**

After `load_dotenv` and before middleware construction, create exactly one
policy and one CORS configuration:

```python
runtime_access_policy = load_runtime_access_policy()
cors_configuration = load_cors_configuration(
    access_policy=runtime_access_policy,
)

app.state.runtime_access_policy = runtime_access_policy
app.state.cors_configuration = cors_configuration
app.state.runtime_access_warning_emitted = False
```

Configure CORS from the frozen values:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_configuration.allowed_origins,
    allow_credentials=False,
    allow_methods=list(cors_configuration.allow_methods),
    allow_headers=list(cors_configuration.allow_headers),
)
app.add_middleware(RuntimeAccessMiddleware)
```

`RuntimeAccessMiddleware.dispatch` reads only `request.app.state`, builds the
Task 1 context, calls `decide_runtime_access`, and returns the bounded response
before `call_next` when denied. It does not re-read `os.environ`.

Emit the loopback-only warning once from `lifespan` by checking and then setting
`app.state.runtime_access_warning_emitted`; do not log from the policy loader or
per request. The warning contains only `loopback_only`, not the secret or
request data.

- [ ] **Step 4: Keep feature-owned authentication independent but UTF-8 safe**

In `review_api.py` and `evidence_verification_api.py`, replace only the
condition `not hmac.compare_digest(supplied, secret)` with
`not credentials_match(supplied, secret)`. Preserve each existing inline
existing `_error` call body verbatim; do not add a shared feature-auth response.

Do not move feature flags, fingerprints, response codes, or persisted authority
into the general policy. Add a correct/incorrect non-ASCII secret regression to
each existing feature API test; the correct value reaches existing behavior and
the wrong value returns the existing `invalid_api_key` without a `500`.

- [ ] **Step 5: Correct the source template in the same PR**

Change only this authentication block in `.env.example`:

```dotenv
# API Authentication. Empty is supported only for the direct loopback source
# runtime; local Compose requires an explicit generated value.
API_SECRET=
```

Do not yet change provider, LangSmith, or MySQL values; Task 6 owns those.

- [ ] **Step 6: Add explicit app-state policy setup for existing tests**

In `tests/conftest.py`, add:

```python
@pytest.fixture
def authenticated_runtime_access(monkeypatch):
    from api.runtime_access import load_runtime_access_policy
    from api.server import app

    monkeypatch.setattr(
        app.state,
        "runtime_access_policy",
        load_runtime_access_policy({"API_SECRET": "test-integration-key"}),
    )
```

This fixture is opt-in and changes only test app state. It does not patch
production peer classification or make environment mutation dynamic.

- [ ] **Step 7: Run Task 3 GREEN and feature-auth regressions**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_runtime_access.py \
  tests/unit/test_auth_middleware.py \
  tests/unit/test_health_endpoint.py \
  tests/integration/test_runtime_access_protocol.py \
  tests/integration/test_durable_review_api.py \
  tests/integration/test_evidence_verification_api.py -q
```

Expected: the full HTTP matrix passes; review/verification retain their exact
existing error contracts and non-ASCII credentials no longer raise.

- [ ] **Step 8: Commit Task 3**

```bash
git add api/server.py api/review_api.py api/evidence_verification_api.py \
  .env.example tests/conftest.py tests/unit/test_auth_middleware.py \
  tests/unit/test_health_endpoint.py \
  tests/integration/test_runtime_access_protocol.py \
  tests/integration/test_durable_review_api.py \
  tests/integration/test_evidence_verification_api.py
git commit -m "feat(api): enforce secure local access"
```

---

### Task 4: Enforce Header-Only WebSocket Access Before Run Identity

**Files:**

- Modify: `api/server.py`
- Modify: `tests/integration/test_runtime_access_protocol.py`
- Modify: `tests/integration/test_run_auxiliary_isolation.py`

**Interfaces:**

- Consumes: `websocket.app.state.runtime_access_policy`, frozen CORS
  configuration, and Task 1 WebSocket context builder.
- Produces: exact handshake order
  `query -> context -> access -> run_id -> get_run -> manager.connect_run`.
- Preserves: `/ws/runs/{run_id}`, run lookup semantics, pong payload, and
  run-scoped connection isolation.

- [ ] **Step 1: Write the real handshake RED matrix**

Use `TestClient` with explicit peer/base URL and a real seeded run. Require:

```python
with client.websocket_connect(
    f"/ws/runs/{run_id}",
    headers={"X-API-Key": "test-integration-key"},
) as websocket:
    websocket.send_text("ping")
    assert websocket.receive_json()["run_id"] == run_id
```

Add rejection cases for:

- missing/wrong configured header;
- `?api_key=` with no header and with a correct header;
- empty secret + remote peer, unsafe Host, or forwarding metadata;
- present Origin when no Origin is configured;
- present Origin different from the exact configured Origin;
- absent Origin for a direct local non-browser client;
- invalid `run_id` and missing run only after access succeeds.

For query, Origin, peer, authority, and invalid-key denials, monkeypatch
`validate_thread_id`, `get_run`, and `manager.connect_run` to raise if called.
Assert all remain uncalled. Assert close reasons contain only a stable decision
code and never the header value, raw query, URL, peer, Host, or Origin. Captured
application logs must also remain clean; the separate Task 5 launcher contract
and Task 6 container command lock the warning-level Uvicorn transport boundary
that TestClient does not exercise.

- [ ] **Step 2: Run Task 4 RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/integration/test_runtime_access_protocol.py \
  tests/integration/test_run_auxiliary_isolation.py \
  -k "websocket or run_websocket" -q
```

Expected: the old endpoint validates `run_id` first, accepts query credentials,
does not validate Origin/peer/authority, and compares strings directly.

- [ ] **Step 3: Implement the ordered handshake gate**

The endpoint starts with this sequence:

```python
context = build_websocket_access_context(websocket)
decision = decide_runtime_access(
    websocket.app.state.runtime_access_policy,
    context,
    allowed_origin=websocket.app.state.cors_configuration.allowed_origin,
)
if not decision.allowed:
    await websocket.close(
        code=4001 if decision.code == "api_key_invalid" else 1008,
        reason=decision.code,
    )
    return

try:
    run_id = validate_thread_id(run_id)
except ValueError:
    await websocket.close(code=1008, reason="Invalid run_id")
    return
```

Only then call `get_run`, then `manager.connect_run`. Delete every read of
`websocket.query_params.get("api_key")`. Do not change receive/send or manager
disconnect behavior.

- [ ] **Step 4: Replace the legacy integration fixture with header auth**

Change the existing successful connection from:

```python
f"/ws/runs/{created['run_id']}?api_key=test-integration-key"
```

to the same path without query plus:

```python
headers={"X-API-Key": "test-integration-key"}
```

Use the `authenticated_runtime_access` fixture and explicit loopback
`TestClient`; do not mutate the loaded policy via environment changes.

- [ ] **Step 5: Run Task 4 GREEN**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/integration/test_runtime_access_protocol.py \
  tests/integration/test_run_auxiliary_isolation.py -q
```

Expected: header-only and empty-secret loopback cases pass, and every unsafe
case proves zero run lookup/connection ownership.

- [ ] **Step 6: Commit Task 4**

```bash
git add api/server.py tests/integration/test_runtime_access_protocol.py \
  tests/integration/test_run_auxiliary_isolation.py
git commit -m "feat(api): secure websocket handshake"
```

---

### Task 5: Preserve Existing API, Proof, Launcher, And Documentation Contracts

**Files:**

- Modify: `api/server.py`
- Modify: `tests/unit/test_runtime_access.py`
- Modify: `tests/integration/test_run_api.py`
- Modify: `tests/integration/test_run_result_api.py`
- Modify: `tests/integration/test_run_dispatch_api.py`
- Modify: `tests/integration/test_run_auxiliary_isolation.py`
- Modify: `tests/integration/test_legacy_runtime_removed.py`
- Modify: `scripts/run_creation_idempotency_proof.py`
- Modify: `scripts/run_dispatch_reconciliation_proof.py`
- Modify: `docs/reference/api-contract.md`
- Modify: `docs/architecture.md`
- Modify: `docs/getting-started.md`
- Modify: `docs/demo-console.md`
- Modify: `docs/AGENT_INTEGRATION.md`
- Modify: `SECURITY.md`
- Modify: `CHANGELOG.md`
- Modify: `tests/unit/test_documentation_contracts.py`
- Modify: `tests/unit/test_demo_console_contracts.py`
- Modify: `tests/unit/test_release_metadata.py`
- Modify: `tests/unit/test_release_presentation_contracts.py`

**Interfaces:**

- Produces: `run_source_server()` and a complete PR A compatibility/document
  boundary.
- Preserves: every existing proof baseline, API/result/Evidence response,
  feature flag, Tool Client, Console, database, frontend, Docker, dependency,
  and release identity.

- [ ] **Step 1: Write launcher RED and implement the source entrypoint**

Patch `api.server.uvicorn.run`, call `run_source_server()`, and require:

```python
run.assert_called_once_with(
    app,
    host="127.0.0.1",
    port=8000,
    reload=False,
    log_level="warning",
)
```

Then implement:

```python
def run_source_server() -> None:
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="warning",
    )

if __name__ == "__main__":
    run_source_server()
```

Passing the already-constructed application object is intentional: reload and
multi-worker mode are disabled, so the supported direct entrypoint must not
re-import `api.server` and construct a second frozen access policy.

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_runtime_access.py -k launcher -q
```

Expected: RED before the function; GREEN after the exact call is implemented.

- [ ] **Step 2: Replace stale environment-mutation assumptions in general API tests**

Apply `pytest.mark.usefixtures("authenticated_runtime_access")` at module scope
in the five named general API files. Every request that relies on the empty
local policy instead uses an explicit loopback `TestClient`:

```python
TestClient(
    app,
    base_url="http://127.0.0.1",
    client=("127.0.0.1", 50000),
)
```

Do not whitelist `testclient` or `testserver` in production. Do not alter route
payload expectations. Keep review/verification tests on their feature-owned
environment behavior.

- [ ] **Step 3: Make existing production proofs explicit about app policy**

Inside each existing proof's bounded environment/patch stack, set and restore:

```python
server.app.state.runtime_access_policy = load_runtime_access_policy(
    {"API_SECRET": "proof-only-api-secret"}
)
```

Use an explicit matching `X-API-Key`; do not change report construction,
baseline bytes, case IDs, boundaries, or Markdown. This prevents pytest
collection order from changing a proof that imports a cached `api.server`.

- [ ] **Step 4: Run the focused compatibility RED/GREEN matrix**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/integration/test_run_api.py \
  tests/integration/test_run_result_api.py \
  tests/integration/test_run_dispatch_api.py \
  tests/integration/test_run_auxiliary_isolation.py \
  tests/integration/test_legacy_runtime_removed.py \
  tests/integration/test_durable_review_api.py \
  tests/integration/test_evidence_verification_api.py \
  tests/unit/test_review_config.py \
  tests/unit/test_decision_research_agent_tool.py -q

PYTHON_DOTENV_DISABLED=1 python scripts/run_creation_idempotency_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_dispatch_reconciliation_proof.py check
```

Expected: no auth-policy collection-order failures and both committed proof
baselines still match exactly.

- [ ] **Step 5: Add public documentation contracts before prose**

Require the PR A docs to contain:

- credential-free source mode means direct peer + literal Host loopback only;
- configured `X-API-Key` remains the Tool Client credential;
- source launcher is `127.0.0.1` without reload;
- the supported source launcher keeps Uvicorn at warning level so rejected
  legacy query credentials are not emitted by info-level WebSocket transport
  logging in source mode;
- Compose warning-level hardening is deferred to PR B and is not claimed as a
  PR A capability;
- CORS/Origin is not authentication;
- WebSocket uses header only and query credentials are removed;
- non-loopback direct use requires a key plus operator-owned TLS and remains
  unsupported as a hosted deployment;
- review and verification keep independent feature-owned gates;
- `.env.example` has `API_SECRET=` and no accepted sentinel key;
- no Docker/Compose/health/capability claim appears before PR B.

Update `test_changelog_preserves_published_release_boundary` so `Unreleased`
equals one exact `### Secure local runtime access` subsection while every
published release section remains byte-for-byte equivalent.

- [ ] **Step 6: Run docs RED, then update only PR A documentation**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_demo_console_contracts.py \
  tests/unit/test_release_metadata.py \
  tests/unit/test_release_presentation_contracts.py -q
```

Expected: RED on missing supported-mode/access/migration text; GREEN after the
named documents and exact `Unreleased` subsection are updated. Keep
`Decision Research Agent v0.1.4` as the current published release and do not
create `docs/releases/v0.1.5.md`.

- [ ] **Step 7: Run the complete PR A gate**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m "not docker"

PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_gate.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_creation_idempotency_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_dispatch_reconciliation_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_failure_cause_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/downstream_consumer_contract.py check \
  --input docs/evidence/downstream-consumer-contract-v1.json
python scripts/check_canonical_identity.py --root .
python scripts/final_presentation_audit.py

cd frontend
npm ci
npm run test
npm run lint
npm run build
npm audit --audit-level=moderate
cd ..

git diff --check origin/main..HEAD
git diff --exit-code origin/main..HEAD -- \
  requirements.txt constraints.txt docker-compose.yml Dockerfile.backend \
  .dockerignore .github/workflows/ci.yml VERSION frontend/package.json \
  frontend/package-lock.json
```

Expected: all non-Docker backend tests and deterministic gates pass; frontend
is unchanged and passes; prohibited diffs are empty. If the local interpreter
lacks a declared dependency, report the exact blocker and obtain the required
proof from the declared environment or CI; do not install an unapproved
dependency or use a stub to claim the full suite passed.

- [ ] **Step 8: Commit PR A docs and compatibility work**

```bash
git add api/server.py tests/unit/test_runtime_access.py tests/conftest.py \
  tests/integration/test_run_api.py tests/integration/test_run_result_api.py \
  tests/integration/test_run_dispatch_api.py \
  tests/integration/test_run_auxiliary_isolation.py \
  tests/integration/test_legacy_runtime_removed.py \
  scripts/run_creation_idempotency_proof.py \
  scripts/run_dispatch_reconciliation_proof.py \
  docs/reference/api-contract.md docs/architecture.md docs/getting-started.md \
  docs/demo-console.md docs/AGENT_INTEGRATION.md SECURITY.md CHANGELOG.md \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_demo_console_contracts.py \
  tests/unit/test_release_metadata.py \
  tests/unit/test_release_presentation_contracts.py
git commit -m "docs(api): publish secure local access boundary"
```

Stop with a clean PR A branch/worktree for full branch-diff review. Do not
start PR B shared integration on this branch.

---

## PR B — Container Delivery And Security Proof

### Task 6: Define And Implement Safe Container Configuration

**Files:**

- Modify: `.env.example`
- Modify: `docker-compose.yml`
- Modify: `Dockerfile.backend`
- Modify: `.dockerignore`
- Create: `tests/unit/test_secure_local_container_contracts.py`
- Modify: `tests/unit/test_deployment_preflight.py`

**Interfaces:**

- Consumes: PR A access behavior and explicit fake operator values.
- Produces: fail-closed Compose configuration, exact image health declaration,
  loopback host publication, reduced privileges, and a narrow build context.

- [ ] **Step 1: Rebase the isolated PR B branch onto landed PR A**

```bash
git fetch origin
git rebase origin/main
```

Expected: the branch contains the merged PR A tree. Confirm
`API_SECRET=` is already empty and no PR A runtime file is modified by the
container lane.

- [ ] **Step 2: Write static container RED contracts**

Assert exact required interpolation and safe declarations:

```python
compose_text = (PROJECT_ROOT / "docker-compose.yml").read_text()
assert "127.0.0.1:8000:8000" in compose_text
assert "${API_SECRET:?" in compose_text
assert "${MYSQL_ROOT_PASSWORD:?" in compose_text
assert "${MYSQL_PASSWORD:?" in compose_text

compose = yaml.safe_load(compose_text)
backend = compose["services"]["backend"]
assert backend["cap_drop"] == ["ALL"]
assert backend["security_opt"] == ["no-new-privileges:true"]
assert backend["env_file"] == [
    "${DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE:-.env}"
]
assert backend["depends_on"]["mysql"]["condition"] == "service_healthy"
assert compose["services"]["mysql"]["healthcheck"]
```

Also assert:

- `.env.example` retains `API_SECRET=` and uses this exact safe subset:

  ```dotenv
  OPENAI_API_KEY=
  TAVILY_API_KEY=
  LANGSMITH_TRACING=false
  LANGSMITH_API_KEY=
  LANGSMITH_HIDE_INPUTS=true
  LANGSMITH_HIDE_OUTPUTS=true
  MYSQL_ROOT_PASSWORD=
  MYSQL_USER=decision_research
  MYSQL_PASSWORD=
  MYSQL_DATABASE=decision_research
  RAGFLOW_API_KEY=
  ```

- source-mode `MYSQL_HOST=localhost` and the existing non-secret provider/model
  configuration remain explicit; Compose continues to override MySQL host to
  `mysql`;
- `LANGSMITH_HIDE_INPUTS=true` and `LANGSMITH_HIDE_OUTPUTS=true` remain enabled
  for an operator who explicitly turns tracing on;
- no `your-` credential sentinel remains;
- `Dockerfile.backend` contains an exact canonical-JSON stdlib HEALTHCHECK,
  starts Uvicorn with `--log-level warning`, and still has no `USER`
  instruction;
- `.dockerignore` excludes `data/`, `.worktrees/`, `frontend/`, pytest/type/
  coverage/tool caches while retaining the durable-HITL evidence allowlist.

- [ ] **Step 3: Run static RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_secure_local_container_contracts.py \
  tests/unit/test_deployment_preflight.py -q
```

Expected: host binding, required variables, health, privileges, safe template,
and build-context assertions fail against the current files.

- [ ] **Step 4: Implement required Compose values and safe template**

Use mapping syntax so required values are visible and testable:

```yaml
services:
  backend:
    ports:
      - "127.0.0.1:8000:8000"
    environment:
      API_SECRET: ${API_SECRET:?Set API_SECRET for local Compose}
    env_file:
      - ${DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE:-.env}
    depends_on:
      mysql:
        condition: service_healthy
    cap_drop:
      - ALL
    security_opt:
      - no-new-privileges:true

  mysql:
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:?Set MYSQL_ROOT_PASSWORD}
      MYSQL_DATABASE: ${MYSQL_DATABASE:-decision_research}
      MYSQL_USER: ${MYSQL_USER:-decision_research}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD:?Set MYSQL_PASSWORD}
```

Add finite MySQL health values and use the container environment rather than a
literal password. Preserve named volumes and the private Compose network.

The backend image health command uses only stdlib and requires both status and
body:

```dockerfile
HEALTHCHECK --interval=5s --timeout=3s --start-period=20s --retries=12 \
  CMD ["python", "-c", "import json; from urllib.request import urlopen; r=urlopen('http://127.0.0.1:8000/health', timeout=2); assert r.status == 200; assert json.load(r) == {'status':'ok','service':'decision-research-agent'}"]
```

Keep the existing
`CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000",
"--log-level", "warning"]` inside the container and do not add `USER`.

- [ ] **Step 5: Prove positive and negative Compose configuration**

Run missing-value cases in a scrubbed environment and require nonzero status
without echoing a supplied value. Both cases use explicit temporary env files,
never the repository `.env`:

```bash
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
touch "$tmpdir/empty.env"
chmod 600 "$tmpdir/empty.env"

env -i PATH="$PATH" HOME="$HOME" \
  DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE="$tmpdir/empty.env" \
  docker compose --env-file "$tmpdir/empty.env" config --quiet

printf '%s\n' \
  'API_SECRET=compose-test-only' \
  'MYSQL_ROOT_PASSWORD=root-test-only' \
  'MYSQL_PASSWORD=app-test-only' \
  'OPENAI_API_KEY=provider-disabled-test-only' \
  'LANGSMITH_TRACING=false' \
  > "$tmpdir/positive.env"
chmod 600 "$tmpdir/positive.env"

env -i PATH="$PATH" HOME="$HOME" \
  DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE="$tmpdir/positive.env" \
  docker compose --env-file "$tmpdir/positive.env" config --quiet
```

The first command is expected to fail on a bounded required-variable message;
the second is expected to exit `0`. Tests capture output and assert no fake
value appears.

- [ ] **Step 6: Run static GREEN and commit**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_secure_local_container_contracts.py \
  tests/unit/test_deployment_preflight.py -q
git diff --check

git add .env.example docker-compose.yml Dockerfile.backend .dockerignore \
  tests/unit/test_secure_local_container_contracts.py \
  tests/unit/test_deployment_preflight.py
git commit -m "feat(container): require secure local configuration"
```

---

### Task 7: Prove The Real Container Runtime And Cleanup Boundary

**Files:**

- Modify: `tests/integration/test_durable_review_container.py`
- Modify: `tests/integration/test_evidence_verification_container.py`
- Modify: `tests/unit/test_durable_review_container.py`
- Modify: `tests/unit/test_secure_local_container_contracts.py`

**Interfaces:**

- Consumes: Task 6 Compose/image contract and existing durable review/
  verification fixtures.
- Produces: bounded real health, inspect, volume, restart, no-provider, and
  cleanup evidence under unique Compose project names.

- [ ] **Step 1: Write helper-isolation and diagnostics RED tests**

Replace the repository `.env` helper with
`_create_isolated_compose_env(tmp_path: Path) -> Path`. It always creates a
mode-`0600` file below `tmp_path`, never opens or mutates `PROJECT_ROOT / ".env"`,
and returns its path. Require fake values for:

```text
API_SECRET
MYSQL_ROOT_PASSWORD
MYSQL_PASSWORD
OPENAI_API_KEY
OPENAI_BASE_URL=http://127.0.0.1:9/v1
TAVILY_API_KEY
LANGSMITH_TRACING=false
```

Give `DockerProject` an `env_file: Path`. Every `_compose` command includes
`("--env-file", str(self.env_file))` before its `-f` arguments, and the
subprocess environment contains
`DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE=str(self.env_file)`.

Do not retain `os.environ.copy()`. Add one helper that starts from a minimal
allowlist of Docker transport/process keys only:

```python
DOCKER_HOST_ENV_KEYS = (
    "PATH",
    "HOME",
    "TMPDIR",
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "DOCKER_TLS_VERIFY",
    "DOCKER_CERT_PATH",
    "XDG_CONFIG_HOME",
)

def build_compose_subprocess_env(
    *,
    env_file: Path,
    docker_config: Path,
    feature_flags: dict[str, str],
) -> dict[str, str]:
    env = {
        key: os.environ[key]
        for key in DOCKER_HOST_ENV_KEYS
        if key in os.environ
    }
    env.update(feature_flags)
    env["DOCKER_CONFIG"] = str(docker_config)
    env["DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE"] = str(env_file)
    return env
```

The helper must not inherit application secrets, provider/database values,
`COMPOSE_*`, or a host-supplied
`DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE`. Unit tests poison all of those host
keys plus a synthetic project-root `.env`, then prove the command, subprocess
environment, and resolved service configuration use only the temporary file
without printing either source or fake values.

`feature_flags` accepts only the existing
`DECISION_RESEARCH_AGENT_ENABLE_DURABLE_HITL` and
`DECISION_RESEARCH_AGENT_ENABLE_EVIDENCE_VERIFICATION` keys and rejects any
other key. Run the Docker availability probe with the same Docker-host
allowlist rather than the full process environment.

Add unit tests that failed `up`, readiness timeout, or assertion failure still
attempt bounded log capture and
`down --rmi local -v --remove-orphans`, and that diagnostic text is
length-bounded and credential-redacted. Before teardown, record any backend
image ID returned by `docker compose images -q backend`; after teardown, require
that exact task-owned image to be absent while the shared `mysql:8.0` image is
untouched.

- [ ] **Step 2: Write runtime RED assertions**

After `up -d --build backend`, require:

```python
assert project.wait_until_healthy(services=("mysql", "backend"))
assert project.get_health() == {
    "status": "ok",
    "service": "decision-research-agent",
}

inspect = project.inspect_backend()
assert inspect["HostConfig"]["CapDrop"] == ["ALL"]
assert "no-new-privileges:true" in inspect["HostConfig"]["SecurityOpt"]
```

Inspect published bindings and require backend `8000/tcp` and MySQL
`3306/tcp` HostIp values equal `127.0.0.1`. Write bounded sentinels inside
`/app/data` and `/app/output`, restart backend, and require both are readable;
delete only the test sentinels afterwards.

Patch or configure every provider endpoint as unreachable, exercise only
health and existing fixture-based durable workflows, and assert no provider
request marker appears in bounded logs.

- [ ] **Step 3: Run the targeted Docker RED**

```bash
DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS=true \
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -q -m docker \
  tests/integration/test_durable_review_container.py \
  tests/integration/test_evidence_verification_container.py
```

Expected: current Compose lacks health/security declarations and exact runtime
inspection helpers; the new assertions fail before implementation is complete.

- [ ] **Step 4: Implement bounded helpers without a second runtime authority**

Extend the existing `DockerProject` rather than introducing another container
controller. Use its explicit temporary `--env-file`, `docker compose ps -q`,
`docker inspect`, in-container stdlib health, and the existing `exec_json`.
Keep each project unique and all cleanup in `finally`.

Freeze and test these per-lifecycle upper bounds:

```python
COMPOSE_UP_TIMEOUT_SECONDS = 480
HEALTH_TIMEOUT_SECONDS = 60
DIAGNOSTIC_TIMEOUT_SECONDS = 30
COMPOSE_CLEANUP_TIMEOUT_SECONDS = 120
MAX_COMPOSE_LIFECYCLE_SECONDS = 690
```

The three function-scoped lifecycles therefore have a combined maximum of
`2070` seconds. The required 60-minute job retains more than 15 minutes for
checkout, dependency installation, collection, assertions, and runner
overhead. Cleanup receives its own reserved timeout and must not reuse an
already-exhausted startup deadline.

`wait_until_healthy` polls finite `.State.Health.Status` values with a monotonic
deadline. On timeout/failure, collect only the final bounded tail of
`docker compose logs --no-color backend mysql`, redact the known fake values,
then run `down --rmi local -v --remove-orphans`. Require empty task-owned
container, volume, network, and recorded-backend-image inventory. Do not call
global Docker prune or remove the shared MySQL image.

- [ ] **Step 5: Run Docker GREEN twice**

```bash
DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS=true \
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -q -m docker

DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS=true \
PYTHON_DOTENV_DISABLED=1 \
python -m pytest -q -m docker
```

Expected: both runs build/reuse layers, reach exact health, preserve current
review/verification restart behavior, inspect security and loopback bindings,
write both volumes, make zero provider calls, and leave no task-owned
containers/volumes/networks/backend images.

- [ ] **Step 6: Commit Task 7**

```bash
git add tests/integration/test_durable_review_container.py \
  tests/integration/test_evidence_verification_container.py \
  tests/unit/test_durable_review_container.py \
  tests/unit/test_secure_local_container_contracts.py
git commit -m "test(container): prove secure local runtime"
```

---

### Task 8: Make The Container Lane A Required Disjoint CI Gate

**Files:**

- Modify: `.github/workflows/ci.yml`
- Modify: `tests/unit/test_secure_local_container_contracts.py`

**Interfaces:**

- Produces: one non-Docker backend job and one required Docker-only job; no
  Docker case may skip or run in both.
- Preserves: existing deterministic gates, Python 3.11 dependency install,
  frontend job, action pinning, and CodeQL workflow behavior.

- [ ] **Step 1: Write CI structure RED assertions**

Parse the workflow and require:

```python
backend_test = workflow["jobs"]["backend"]["steps"][-1]
assert '-m "not docker"' in backend_test["run"]

container = workflow["jobs"]["container"]
assert container["name"] == "Secure Local Runtime Containers"
assert container["timeout-minutes"] == 60
docker_step = container["steps"][-1]
assert docker_step["env"]["DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS"] == "true"
assert docker_step["run"] == "python -m pytest -q -m docker"
```

Also assert no Docker-marked test command appears in the backend job and no
non-Docker/full-suite command appears in the container job. Task 9 adds the
deterministic proof to the backend job after its script exists.

- [ ] **Step 2: Run CI contract RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_secure_local_container_contracts.py -k ci -q
```

Expected: no required container job or disjoint marker commands exist.

- [ ] **Step 3: Split the jobs without duplicating tests**

Keep all existing backend proof steps and change only the final test command:

```yaml
- name: Run tests
  env:
    PYTHON_DOTENV_DISABLED: '1'
  run: python -m pytest -q -m "not docker"
```

Add one job with the same checkout, Python 3.11 setup, cache, and locked install:

```yaml
container:
  name: Secure Local Runtime Containers
  runs-on: ubuntu-latest
  timeout-minutes: 60
  steps:
    - uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0
    - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1
      with:
        python-version: '3.11'
        cache: pip
        cache-dependency-path: |
          requirements.txt
          constraints.txt
    - name: Install dependencies
      run: pip install --no-deps -r constraints.txt
    - name: Run required container tests
      env:
        PYTHON_DOTENV_DISABLED: '1'
        DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS: 'true'
      run: python -m pytest -q -m docker
```

Do not create a second container job or set the required-Docker flag on the
non-Docker job.

- [ ] **Step 4: Run CI GREEN and local command parity**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_secure_local_container_contracts.py -k ci -q
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m "not docker"
DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS=true \
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m docker
```

Expected: unit contract, complete non-Docker suite, and Docker-only suite pass
with disjoint collection counts.

- [ ] **Step 5: Commit Task 8**

```bash
git add .github/workflows/ci.yml \
  tests/unit/test_secure_local_container_contracts.py
git commit -m "ci(container): require secure runtime checks"
```

---

### Task 9: Add Strict Deterministic Proof Contracts And CLI

**Files:**

- Create: `scripts/secure_local_runtime_contracts.py`
- Create: `scripts/secure_local_runtime_proof.py`
- Create: `tests/unit/test_secure_local_runtime_contracts.py`
- Create: `tests/integration/test_secure_local_runtime_proof.py`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**

- Produces: schema `dra.secure-local-runtime.v1`, exact 16-case report,
  deterministic JSON/Markdown serializers, and bounded `build`/`check` CLI.
- Consumes: actual `RuntimeAccessMiddleware`, actual WebSocket endpoint/policy,
  actual CORS parser, actual source launcher, and checked-in container files.

- [ ] **Step 1: Freeze report identity, order, observations, and limits in RED tests**

Use this exact ordered case tuple:

```python
EXPECTED_CASE_IDS = (
    "source_launcher_loopback_no_reload",
    "http_empty_secret_ipv4_loopback_allowed",
    "http_empty_secret_ipv6_loopback_allowed",
    "http_empty_secret_non_loopback_rejected",
    "http_empty_secret_unknown_peer_rejected",
    "http_empty_secret_non_loopback_authority_rejected",
    "http_empty_secret_forwarded_rejected",
    "http_configured_secret_invalid_rejected",
    "http_configured_secret_valid_all_peers",
    "websocket_header_credential_accepted",
    "websocket_query_credential_rejected",
    "websocket_invalid_origin_rejected",
    "cors_invalid_origin_rejected",
    "cors_empty_secret_remote_origin_rejected",
    "compose_loopback_required_secrets",
    "container_health_privilege_contract",
)
```

Freeze the observation schema and successful values as well as case order:

```python
EXPECTED_OBSERVATIONS = {
    "source_launcher_loopback_no_reload": {
        "host": "127.0.0.1",
        "port": 8000,
        "reload": False,
        "log_level": "warning",
    },
    "http_empty_secret_ipv4_loopback_allowed": {
        "decision_code": "allowed_loopback",
        "http_status": 200,
        "route_reached": True,
    },
    "http_empty_secret_ipv6_loopback_allowed": {
        "decision_code": "allowed_loopback",
        "http_status": 200,
        "route_reached": True,
    },
    "http_empty_secret_non_loopback_rejected": {
        "decision_code": "api_auth_not_configured",
        "http_status": 503,
        "route_reached": False,
    },
    "http_empty_secret_unknown_peer_rejected": {
        "decision_code": "api_auth_not_configured",
        "http_status": 503,
        "route_reached": False,
    },
    "http_empty_secret_non_loopback_authority_rejected": {
        "decision_code": "local_authority_required",
        "http_status": 503,
        "route_reached": False,
    },
    "http_empty_secret_forwarded_rejected": {
        "decision_code": "forwarded_request_rejected",
        "http_status": 503,
        "route_reached": False,
    },
    "http_configured_secret_invalid_rejected": {
        "decision_code": "api_key_invalid",
        "http_status": 401,
        "route_reached": False,
    },
    "http_configured_secret_valid_all_peers": {
        "decision_code": "allowed_api_key",
        "loopback_route_reached": True,
        "non_loopback_route_reached": True,
    },
    "websocket_header_credential_accepted": {
        "decision_code": "allowed_api_key",
        "run_lookup_observed": True,
        "connection_observed": True,
    },
    "websocket_query_credential_rejected": {
        "decision_code": "query_credential_rejected",
        "close_code": 1008,
        "run_lookup_observed": False,
        "connection_observed": False,
    },
    "websocket_invalid_origin_rejected": {
        "decision_code": "origin_not_allowed",
        "close_code": 1008,
        "run_lookup_observed": False,
        "connection_observed": False,
    },
    "cors_invalid_origin_rejected": {
        "configuration_code": "cors_origin_invalid",
        "construction_rejected": True,
    },
    "cors_empty_secret_remote_origin_rejected": {
        "configuration_code": "cors_origin_requires_authenticated_runtime",
        "construction_rejected": True,
    },
    "compose_loopback_required_secrets": {
        "backend_host_ip": "127.0.0.1",
        "mysql_host_ip": "127.0.0.1",
        "api_secret_required": True,
        "mysql_root_password_required": True,
        "mysql_password_required": True,
        "service_env_file_parameterized": True,
    },
    "container_health_privilege_contract": {
        "backend_healthcheck_declared": True,
        "mysql_healthcheck_declared": True,
        "cap_drop_all_declared": True,
        "no_new_privileges_declared": True,
        "uvicorn_log_level": "warning",
        "container_runtime_scope": "separate_required_lane",
    },
}
```

The production-path builder may use a bounded spy around the real access
decision to observe the stable allowed code, but it must not calculate an
expected code in parallel logic. Case 16 deliberately records declarations and
the separate lane boundary; it does not include a false `runtime_observed`
field or imply that deterministic proof started a container.

Require exact top-level keys:

```python
{
    "schema_version",
    "status",
    "source",
    "cases",
    "boundaries",
    "limits",
}
```

Use `schema_version="dra.secure-local-runtime.v1"`, `status="valid"`, and
`source="production_path_deterministic_local"`. Every case has only
`case_id`, `status="passed"`, and a case-specific exact `observations` mapping.
The validator rejects missing/extra/reordered cases, extra observation keys,
bool-as-int confusion, any value that differs from `EXPECTED_OBSERVATIONS`,
unknown codes, dynamic commit IDs, paths, credentials, provider values, or
extra top-level fields.

Freeze these boundaries:

```python
BOUNDARIES = {
    "source_loopback_access": "proven",
    "authenticated_api_key_access": "proven",
    "websocket_header_only_access": "proven",
    "cors_exact_origin": "proven",
    "container_configuration": "proven",
    "container_runtime": "separate_required_lane",
    "hosted_deployment": "not_claimed",
    "live_provider_result": "not_observed",
}
```

and limits that state this is deterministic local contract evidence, not TLS,
identity/RBAC, hosted-operation certification, provider quality, or a
replacement for the Docker runtime lane.

- [ ] **Step 2: Run proof-contract RED**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_secure_local_runtime_contracts.py -q
```

Expected: collection fails because the contract module does not exist.

- [ ] **Step 3: Implement strict validators and serializers**

Follow the repository's existing proof conventions:

Use the exact interface
`validate_report(report: dict[str, Any]) -> dict[str, Any]` and this serializer:

```python
def serialize_report(report: dict[str, Any]) -> bytes:
    validate_report(report)
    return (
        json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
```

`render_markdown(report: dict[str, Any]) -> str` begins with
`# Secure Local Runtime v1 Proof`, renders the ordered case table, then ordered
boundaries and limits, and always ends with one newline.

Validation uses exact type checks (`type(value) is bool/int/str`) and exact
key sets; it does not accept Pydantic/JSON coercion. Markdown carries every
case, boundary, and limit in stable order and never renders a raw peer, Host,
Origin, query, credential, local path, exception, or commit SHA.

- [ ] **Step 4: Write production-path and mutation RED tests**

Require the proof builder to:

- patch `uvicorn.run`, invoke `run_source_server()`, and observe exact host,
  port, reload;
- pass HTTP cases through the production `RuntimeAccessMiddleware` with
  explicit Starlette peer/base URL;
- pass WebSocket cases through the real `/ws/runs/{run_id}` endpoint with
  app-state policy and a temporary application database;
- call the actual CORS loader for both invalid cases;
- inspect the actual Compose/Dockerfile/template/build-context artifacts for
  cases 15–16.

Mutation tests must fail closed when they:

```python
monkeypatch.setattr(
    server,
    "decide_runtime_access",
    lambda *_args, **_kwargs: AccessDecision(
        allowed=True,
        code="allowed_loopback",
    ),
)
```

restore query credential acceptance, widen backend mapping to `8000:8000`,
remove `cap_drop`, return a false observation, reorder cases, or add a secret/
path to report limits. Patch the production symbol actually used by the proof;
a mutation that misses the real execution branch is not accepted.

- [ ] **Step 5: Implement the bounded proof builder and CLI**

Expose exact interfaces `build_report() -> dict[str, Any]` and
`main(argv: list[str] | None = None) -> int`.

Build every production observation twice and require serialized JSON and
Markdown byte equality before returning. CLI syntax is exact:

```bash
python scripts/secure_local_runtime_proof.py build \
  --json-output /tmp/secure-local-runtime.json \
  --markdown-output /tmp/secure-local-runtime.md

python scripts/secure_local_runtime_proof.py check \
  --json-baseline docs/evidence/secure-local-runtime-v1.json \
  --markdown-baseline docs/evidence/secure-local-runtime-v1.md
```

Implement a custom `argparse.ArgumentParser.error` boundary so invalid/missing
arguments, missing/corrupt/oversized/nonregular/symlink baselines, aliasing
outputs, and write/replace failures return exit `1`, empty stdout, and exactly:

```json
{"status":"invalid","code":"secure_local_runtime_proof_invalid"}
```

on one stderr line. `--help` returns `0`; module import is silent. Bound reads
to `1_000_000` bytes. Validate both output paths before building, stage sibling
temporary files, `fsync`, and use `os.replace`; remove all temporary files on
failure. Success lines are exactly `{"status":"built"}` and
`{"status":"valid","match":true}`.

- [ ] **Step 6: Run proof unit/integration GREEN**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_secure_local_runtime_contracts.py \
  tests/integration/test_secure_local_runtime_proof.py -q
```

Expected: strict report, production path, every mutation, CLI, bounded I/O,
import silence, and byte-stability tests pass.

- [ ] **Step 7: Add the proof to the backend CI job**

Insert before non-Docker pytest:

```yaml
- name: Run secure local runtime proof
  env:
    PYTHON_DOTENV_DISABLED: '1'
  run: python scripts/secure_local_runtime_proof.py check
```

Do not add this proof to the container job; container runtime remains its own
gate.

- [ ] **Step 8: Commit Task 9 implementation before baselines**

```bash
git add scripts/secure_local_runtime_contracts.py \
  scripts/secure_local_runtime_proof.py \
  tests/unit/test_secure_local_runtime_contracts.py \
  tests/integration/test_secure_local_runtime_proof.py \
  .github/workflows/ci.yml
git commit -m "feat(proof): define secure runtime evidence"
```

---

### Task 10: Commit Evidence, Operations, Discovery, And Full PR B Verification

**Files:**

- Create: `docs/evidence/secure-local-runtime-v1.json`
- Create: `docs/evidence/secure-local-runtime-v1.md`
- Create: `docs/operations/secure-local-runtime.md`
- Modify: `docs/evidence/README.md`
- Modify: `README.md`
- Modify: `README_CN.md`
- Modify: `docs/README.md`
- Modify: `docs/architecture.md`
- Modify: `docs/getting-started.md`
- Modify: `SECURITY.md`
- Modify: `CHANGELOG.md`
- Modify: `tests/unit/test_documentation_contracts.py`
- Modify: `tests/unit/test_release_metadata.py`
- Modify: `tests/unit/test_release_presentation_contracts.py`

**Interfaces:**

- Produces: committed deterministic baselines, supported local operations, and
  complete PR B discoverability.
- Preserves: `v0.1.4` published identity and every historical release section.

- [ ] **Step 1: Build fresh candidate evidence outside tracked paths**

```bash
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
PYTHON_DOTENV_DISABLED=1 python scripts/secure_local_runtime_proof.py build \
  --json-output "$tmpdir/report.json" \
  --markdown-output "$tmpdir/report.md"
```

Run it twice into separate files and require `cmp` for both formats. Scan the
candidates for secret markers, `api_key=` query material, absolute paths,
environment values, exception text, commit hashes, and provider facts before
copying the exact reviewed bytes to the two tracked evidence files.

- [ ] **Step 2: Write baseline RED/check tests, then commit exact evidence**

Before adding the files, run:

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/secure_local_runtime_proof.py check
```

Expected: exit `1` because baselines do not exist. Add the reviewed JSON and
Markdown, then require two consecutive checks to return the exact valid line
and byte-identical stdout.

- [ ] **Step 3: Add documentation contracts before prose**

Require the final feature docs to distinguish:

- source loopback/empty-secret vs authenticated Compose;
- container-internal `0.0.0.0` vs host `127.0.0.1` publication;
- CORS/Origin vs authentication;
- shared API key vs TLS, identity, authorization, and hosted support;
- exact process health vs database/provider/research readiness;
- deterministic proof vs required Docker lane vs later tag-archive smoke;
- `cap_drop`/no-new-privileges vs the explicitly retained root UID;
- required API/MySQL variables, safe generation, migration, rollback, and
  existing-volume compatibility;
- default repository `.env` operation and the optional
  `DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE` path override used for isolated
  environments without creating another runtime mode;
- no provider/model/tool request in the proof or smoke.

Update `Unreleased` to exactly two ordered subsections:

1. `### Secure local runtime access` from PR A.
2. `### Secure local container delivery` from PR B.

Historical `0.1.4` and earlier sections must remain identical. Do not create a
`0.1.5` heading or release notes yet.

- [ ] **Step 4: Run docs RED, implement prose, then GREEN**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_release_metadata.py \
  tests/unit/test_release_presentation_contracts.py -q
```

Expected: RED before the operations/evidence/discovery text; GREEN after all
named docs and indexes are updated without premature publication claims.

- [ ] **Step 5: Run the full PR B verification matrix**

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/secure_local_runtime_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/secure_local_runtime_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_gate.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_creation_idempotency_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_dispatch_reconciliation_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_failure_cause_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/downstream_consumer_contract.py check \
  --input docs/evidence/downstream-consumer-contract-v1.json

PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m "not docker"
DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS=true \
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m docker

python scripts/check_canonical_identity.py --root .
python scripts/final_presentation_audit.py

cd frontend
npm ci
npm run test
npm run lint
npm run build
npm audit --audit-level=moderate
cd ..

git diff --check origin/main..HEAD
git diff --exit-code origin/main..HEAD -- \
  requirements.txt constraints.txt VERSION frontend/package.json \
  frontend/package-lock.json api/run_migrations.py \
  docs/evidence/downstream-consumer-contract-v1.json
```

Additionally inspect the final Docker inventory and require no task-owned
containers, volumes, networks, or recorded backend images after the test. Scan
new public artifacts for private markers, credentials, raw query credentials,
local paths, provider payloads, and unsupported hosted/non-root claims.

Enforce the PR B boundary relative to the rebased PR A base:

```bash
git diff --exit-code origin/main..HEAD -- \
  api/ frontend/src/ VERSION frontend/package.json \
  frontend/package-lock.json requirements.txt constraints.txt \
  pyproject.toml
```

The command must be empty. Container/proof/docs work must not reopen runtime
access implementation, frontend behavior, version identity, or dependencies.

- [ ] **Step 6: Commit Task 10 and stop for PR B review**

```bash
git add docs/evidence/secure-local-runtime-v1.json \
  docs/evidence/secure-local-runtime-v1.md \
  docs/operations/secure-local-runtime.md docs/evidence/README.md \
  README.md README_CN.md docs/README.md docs/architecture.md \
  docs/getting-started.md SECURITY.md CHANGELOG.md \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_release_metadata.py \
  tests/unit/test_release_presentation_contracts.py
git commit -m "docs(runtime): publish secure local evidence"
```

Stop with a clean PR B branch/worktree for full branch-diff review. Do not
prepare version metadata on the feature branch.

---

## PR C — v0.1.5 Release Preparation

### Task 11: Prepare Pure Release Metadata After Both Features Land

**Files:**

- Modify: `VERSION`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Modify: `CHANGELOG.md`
- Modify: `SECURITY.md`
- Modify: `README.md`
- Modify: `README_CN.md`
- Modify: `docs/README.md`
- Create: `docs/releases/v0.1.5.md`
- Modify: `tests/unit/test_release_metadata.py`
- Modify: `tests/unit/test_documentation_contracts.py`

**Interfaces:**

- Consumes: merged and CI-passing PR A + PR B on `origin/main`.
- Produces: local `v0.1.5` release-preparation branch only. Tagging, GitHub
  Release publication, tag-archive smoke, and deployment remain separate.

- [ ] **Step 1: Create a fresh branch only after exact main verification**

```bash
git fetch origin
git status --short --branch
git log -1 --format=%H origin/main
```

Require clean `main == origin/main`, no open feature PR, and both reviewed
feature trees retained. Create a fresh isolated `codex/v0-1-5-release` branch;
do not continue from a feature branch.

- [ ] **Step 2: Add release contracts and obtain real RED**

Add `V015_RELEASE_NOTES` and require exact `0.1.5` identity across the version
file, frontend package, and lock root/package entries. Require ordering:

```text
Unreleased -> 0.1.5 -> 0.1.4 -> 0.1.3 -> 0.1.2 -> 0.1.1 -> 0.1.0
```

Require `Unreleased` empty, the exact two feature subsections archived under
`0.1.5`, all historical sections unchanged, current release discovery, and
release notes containing:

- Supported Surface;
- Changes;
- Compatibility And Migration;
- Rollback;
- Required Verification;
- Known Limits;
- empty-secret source loopback boundary;
- Compose required values and loopback publication;
- WebSocket header-only correction;
- deterministic vs Docker vs archive-smoke evidence;
- root-container residual limitation;
- no TLS/identity/RBAC/hosted/production/provider claim.

Also forbid claims that tag, GitHub Release, archive smoke, deployment, or live
research has already completed.

Run:

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_release_metadata.py \
  tests/unit/test_documentation_contracts.py -q
```

Expected: RED because identity is still `0.1.4`, `Unreleased` is nonempty, and
release notes/discovery do not exist.

- [ ] **Step 3: Commit release contracts separately**

```bash
git add tests/unit/test_release_metadata.py \
  tests/unit/test_documentation_contracts.py
git commit -m "test(release): define v0.1.5 preparation contracts"
```

- [ ] **Step 4: Implement exact release metadata**

Capture the actual preparation calendar date once with:

```bash
release_date="$(date +%F)"
```

Use that literal consistently in the `0.1.5` CHANGELOG heading and release
notes. Change only the two lockfile version fields; compare a normalized copy
with those two fields removed to prove dependency/integrity semantics are
unchanged. Keep runtime, API, DB, proof baselines, CI, dependencies, spec, and
plan untouched.

- [ ] **Step 5: Run release GREEN and all release gates**

```bash
PYTHON_DOTENV_DISABLED=1 python -m pytest \
  tests/unit/test_release_metadata.py \
  tests/unit/test_documentation_contracts.py \
  tests/unit/test_release_presentation_contracts.py \
  tests/unit/test_demo_console_contracts.py -q

PYTHON_DOTENV_DISABLED=1 python scripts/secure_local_runtime_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/agent_evaluation_gate.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_creation_idempotency_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_dispatch_reconciliation_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/run_failure_cause_proof.py check
PYTHON_DOTENV_DISABLED=1 python scripts/downstream_consumer_contract.py check \
  --input docs/evidence/downstream-consumer-contract-v1.json

PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m "not docker"
DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS=true \
PYTHON_DOTENV_DISABLED=1 python -m pytest -q -m docker

python scripts/check_canonical_identity.py --root .
python scripts/final_presentation_audit.py

cd frontend
npm ci
npm run test
npm run lint
npm run build
npm audit --audit-level=moderate
cd ..

git diff --check origin/main..HEAD

actual_files="$(git diff --name-only origin/main..HEAD | LC_ALL=C sort)"
expected_files="$(cat <<'EOF'
CHANGELOG.md
README.md
README_CN.md
SECURITY.md
VERSION
docs/README.md
docs/releases/v0.1.5.md
frontend/package-lock.json
frontend/package.json
tests/unit/test_documentation_contracts.py
tests/unit/test_release_metadata.py
EOF
)"
test "$actual_files" = "$expected_files"
```

Require no dependency, constraints, migration, runtime, CI, proof-baseline, or
historical-release drift. A local environment blocker is reported precisely;
it is not converted into a passing claim with import stubs.

- [ ] **Step 6: Commit release metadata and stop before publication**

```bash
git add VERSION frontend/package.json frontend/package-lock.json CHANGELOG.md \
  SECURITY.md README.md README_CN.md docs/README.md \
  docs/releases/v0.1.5.md
git commit -m "docs(release): prepare v0.1.5 metadata"
```

Stop with a clean local release branch for review. Do not create a tag, GitHub
Release, deployment, or tag-archive smoke in this task.

---

## Post-Publication Archive Smoke (Separately Authorized)

After a separately authorized annotated `v0.1.5` tag and public GitHub Release,
verify the exact tag archive in a fresh temporary directory:

1. record archive SHA-256 and version/package/lock/release-note identity;
2. create a mode-`0600` `.env` containing only fake API/MySQL/provider values;
3. run `docker compose config --quiet` without printing resolved configuration;
4. build and start a uniquely named Compose project from the archive;
5. wait with a bounded deadline for MySQL and backend health;
6. assert `GET http://127.0.0.1:8000/health` returns exactly
   `{"status":"ok","service":"decision-research-agent"}`;
7. inspect loopback-only backend/MySQL publication, `CapDrop=ALL`,
   `no-new-privileges`, and data/output volume writability;
8. prove no provider/model/tool request ran;
9. always remove only that project's containers, volumes, networks,
   task-built backend image, archive, extracted tree, and fake env; preserve
   shared base images and never run global Docker prune.

Report this as local release-archive runtime evidence, not deployment,
production readiness, hosted security certification, or live-provider quality.

---

## Plan Self-Review Checklist

- Spec coverage: every approved goal, failure-matrix row, PR boundary,
  compatibility rule, release gate, documentation distinction, and residual
  limit maps to Tasks 1–11 or the separately authorized archive smoke.
- Intermediate-main safety: PR A corrects `.env.example` `API_SECRET=` in the
  same series that rejects the sentinel; PR B cannot leave a documented value
  that runtime rejects.
- Access order: HTTP policy runs before route behavior; WebSocket query/context/
  access runs before run identity, database lookup, and connection ownership.
- CI ownership: non-Docker and Docker tests are disjoint; there is one required
  container lane, no silent skip, and the aggregate lifecycle maximum remains
  below the job timeout with cleanup headroom.
- Test isolation: Compose subprocesses use a minimal host-environment allowlist,
  explicit temporary env files, and exact task-owned image cleanup.
- Change boundaries: PR B proves prohibited paths are unchanged relative to its
  PR A base; PR C proves an exact release-metadata changed-file allowlist.
- Framework boundary: FastAPI/Starlette/Pydantic/Docker primitives are reused;
  Agent middleware, LangGraph, DeepAgents, LangSmith, DB, and business
  authority remain unchanged.
- Future evolution: the application-owned policy seam can add a later
  credential/principal adapter without changing run/result/Evidence routes;
  non-root volume migration remains independent.
- Unresolved-token scan: the plan contains no deferred implementation marker
  or angle-bracket substitution token.
- Type consistency: policy/context/decision names, access codes, CORS fields,
  proof schema, case IDs, environment keys, and output filenames are identical
  across producing and consuming tasks.
