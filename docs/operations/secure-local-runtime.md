# Secure Local Runtime

This runbook covers the supported local source and Docker Compose launch
boundaries. It preserves the same FastAPI application, API paths, run/result
contracts, application-database authority, and feature-owned review and
Evidence verification gates in both launch forms.

## Choose The Local Launch Form

The source launcher is the bounded credential-free path:

```bash
python api/server.py
```

With `API_SECRET=` it accepts protected requests only when the direct peer and
literal Host are both loopback. It passes the already-constructed application
to Uvicorn, binds `127.0.0.1`, disables reload, and uses warning-level logging.

Compose is the authenticated local container path. It requires explicit
`API_SECRET`, `MYSQL_ROOT_PASSWORD`, and `MYSQL_PASSWORD` values before
configuration succeeds. The shared API key is a local compatibility
credential; it does not provide TLS, caller identity, authorization, RBAC, or
hosted-operation support. CORS and Origin checks are not authentication, and
authenticated WebSocket clients must use `X-API-Key` rather than a query
credential.

The backend listens on container-internal `0.0.0.0:8000` so other services on
the private Compose network can reach it. Host publication remains exact and
loopback-only:

```yaml
backend: 127.0.0.1:8000:8000
mysql:   127.0.0.1:3306:3306
```

Container-internal listening does not widen the host publication boundary.
Neither launch form is a supported hosted deployment.

## Prepare Required Values

The default repository `.env` workflow remains supported. Generate the three
required values and create a new mode-`0600` file without printing or placing a
credential in command arguments:

```bash
python - <<'PY'
from pathlib import Path
import os
import secrets

text = Path(".env.example").read_text(encoding="utf-8")
for name in ("API_SECRET", "MYSQL_ROOT_PASSWORD", "MYSQL_PASSWORD"):
    needle = f"{name}=\n"
    if text.count(needle) != 1:
        raise SystemExit("environment template contract changed")
    text = text.replace(
        needle,
        f"{name}={secrets.token_urlsafe(48)}\n",
        1,
    )
descriptor = os.open(".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
    handle.write(text)
PY
```

The generated file sets all three required assignments:

```dotenv
API_SECRET=
MYSQL_ROOT_PASSWORD=
MYSQL_PASSWORD=
```

The empty assignments above show names only; Compose deliberately rejects
missing or empty values. Do not reuse the root password as the application
password, commit the completed file, put credentials in Compose command
arguments, or print resolved configuration. Compose delivers the non-empty root
credential to MySQL while explicitly overriding `MYSQL_ROOT_PASSWORD` to an
empty value in the backend service environment.

For an isolated environment, use a different mode-`0600` file through both
Compose interpolation and the service env-file seam:

```bash
export DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE="$PWD/.env.secure-local"
docker compose \
  --env-file "$DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE" \
  config --quiet
```

`DECISION_RESEARCH_AGENT_COMPOSE_ENV_FILE` parameterizes the same Compose
delivery path and does not create a second runtime mode or credential
authority. Normal operators can continue using the default repository `.env`.

## Validate And Start Compose

Validate without rendering resolved secrets, then build and start the backend
and its health-gated MySQL dependency:

```bash
docker compose config --quiet
docker compose up -d --build backend
docker compose ps
```

Missing or empty required values fail closed during `docker compose config
--quiet`. MySQL must become healthy before the backend starts. The backend
image declares an exact stdlib health check whose successful response is:

```json
{"status":"ok","service":"decision-research-agent"}
```

The response establishes bounded backend process/service identity. It is not
evidence of database, provider, model, tool, or research readiness. MySQL
readiness remains a separate Compose dependency condition.

The backend container uses warning-level Uvicorn logging. Compose also applies:

```yaml
cap_drop:
  - ALL
security_opt:
  - no-new-privileges:true
```

These settings reduce ambient privilege, but the root UID is intentionally
retained for compatibility with existing root-owned `data` and `output`
volumes. The current image does not claim non-root operation, a read-only root
filesystem, or isolation equivalent to a hosted security boundary.

## Evidence Layers

Three evidence layers have different authority:

1. The deterministic proof runs production access, WebSocket, CORS, source
   launcher, and checked-in container configuration paths without starting
   Docker:

   ```bash
   PYTHON_DOTENV_DISABLED=1 \
     python scripts/secure_local_runtime_proof.py check
   ```

2. The required Docker lane owns real local image build, MySQL/backend health,
   exact health JSON, loopback bindings, privilege inspection, volume
   persistence across restart, and task-owned cleanup:

   ```bash
   DECISION_RESEARCH_AGENT_REQUIRE_DOCKER_TESTS=true \
   PYTHON_DOTENV_DISABLED=1 \
     python -m pytest -q -m docker
   ```

3. A tag-archive smoke is a later, separately authorized post-publication
   check. It has not run for unreleased work and cannot be replaced by either
   repository proof.

The deterministic proof does not invoke provider, model, or tool execution.
The required Docker lane uses fixed local fixtures, fake credentials, and an
unreachable provider endpoint; no provider, model, or tool request was observed
on those paths. Any later tag-archive smoke must preserve that zero-request
boundary. None of these layers proves provider quality, research quality,
TLS, identity, RBAC, hosted security, or production deployment.

## Migration And Existing Volumes

This container hardening adds no database migration, table change, volume
format change, dependency change, or application API change. Existing named
SQLite/MySQL, `data`, and `output` volumes remain compatible; the retained root
UID avoids an unapproved ownership migration.

Compose users must replace legacy or example API and database values with
explicit local values before configuration succeeds. Changing
`MYSQL_ROOT_PASSWORD` or `MYSQL_PASSWORD` in an env file does not by itself
rotate credentials inside an already initialized MySQL data volume; use a
database-authorized rotation procedure and update the application value as one
coordinated operation.

A future non-root image requires a separate migration proving fresh and
existing volume ownership, preserved sentinel data, custom mounts, restart,
and rollback. Do not recursively change ownership of an unresolved host path.

## Rollback

Stop the current stack without deleting persisted volumes:

```bash
docker compose down --remove-orphans
```

Use normal version-controlled configuration rollback, then re-run `docker
compose config --quiet` before restart. No database or volume-format rollback
is required by this change, and rollback does not generate, rotate, persist,
or destroy key material.

Do not add `-v` unless discarding the task's named volumes is explicit and the
data has been handled separately. Do not use `docker system prune` or a global
image/volume prune. Restoring an older configuration may reopen broad host
bindings or credential defaults; treat that as a security regression rather
than a recommended steady state.
