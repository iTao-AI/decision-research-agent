# Security Policy

Decision Research Agent v0.1.4 ships the FastAPI backend, Python Tool Client,
single-node application-owned run dispatch reconciliation and durable failure cause
projection, operator scripts, tests, documentation, and the separately
built Agent Research Operations Console. The loopback-only console does not accept credentials
and is not a publicly hosted service.

## Reporting A Vulnerability

Do not disclose suspected vulnerabilities in public Issues or pull requests.

Use GitHub private vulnerability reporting for this repository. Include the
affected behavior, reproduction steps, expected impact, and any suggested
mitigation.

## Supported Surface

Security reports should concern repository code, dependencies, public API/CLI
contracts, migration and recovery scripts, Docker configuration, or documented
runtime behavior.

API keys must be provided through environment variables. Do not pass API keys on
the command line, commit them to source control, include them in logs, or paste
them into issues, pull requests, release notes, or Agent conversations.

## Unreleased / Current Main Security Controls

The controls below describe the repository's current `main` branch after the
v0.1.4 release. They are not part of the published v0.1.4 surface.

The source template uses `API_SECRET=` for credential-free loopback-only use;
no sentinel value is accepted. In that mode, the direct peer and literal Host
must both be loopback. Configuring `API_SECRET` requires the matching
`X-API-Key` on protected HTTP and WebSocket requests. CORS and Origin checks
are not authentication, and WebSocket query credentials are rejected.

The source launcher binds `127.0.0.1` with reload disabled. The source and
Compose launchers use Uvicorn warning-level logging so rejected legacy query
credentials are not emitted by info-level WebSocket transport logging. Compose
requires non-empty `API_SECRET`, `MYSQL_ROOT_PASSWORD`, and `MYSQL_PASSWORD`,
and publishes backend/MySQL only on host `127.0.0.1`; the backend's
container-internal `0.0.0.0` listener remains inside the Compose network. The
MySQL root credential value is delivered only to MySQL; the backend explicitly
receives an empty `MYSQL_ROOT_PASSWORD` value.

Compose declares bounded backend/MySQL health, drops all backend capabilities,
and enables `no-new-privileges`. The health response proves process/service
identity, not database, provider, model, tool, or research readiness. The
container retains its root UID for compatibility with existing `data` and
`output` volumes; non-root operation has not been delivered. The shared API
key does not supply TLS, caller identity, authorization, or RBAC.

Non-loopback direct use is not a supported hosted deployment. It also requires
operator-owned TLS. Controlled review and Evidence verification retain
independent feature-owned gates. The deterministic proof and required Docker
lane use no live provider, model, or tool request and do not certify hosted or
production security.

LangSmith traces are privacy-first by default. Keep inputs and outputs hidden
unless a local, low-sensitivity diagnostic task explicitly requires temporary
full trace visibility.

Treat caller-provided request data, model output, tool responses, external
service responses, generated reports, and persisted artifacts as untrusted
input.

## Out Of Scope

- Public bug bounty commitments.
- Hosted service operations outside this repository.
- Hosted console operations, RBAC, multi-tenant, or multi-replica deployments
  that are not part of v0.1.4.
