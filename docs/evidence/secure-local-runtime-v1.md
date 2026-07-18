# Secure Local Runtime v1 Proof

Status: valid deterministic local production-path contract proof.

## Cases

| Case | Status | Observations |
|---|---|---|
| `source_launcher_loopback_no_reload` | passed | `host=127.0.0.1`<br>`port=8000`<br>`reload=false`<br>`log_level=warning` |
| `http_empty_secret_ipv4_loopback_allowed` | passed | `decision_code=allowed_loopback`<br>`http_status=200`<br>`route_reached=true` |
| `http_empty_secret_ipv6_loopback_allowed` | passed | `decision_code=allowed_loopback`<br>`http_status=200`<br>`route_reached=true` |
| `http_empty_secret_non_loopback_rejected` | passed | `decision_code=api_auth_not_configured`<br>`http_status=503`<br>`route_reached=false` |
| `http_empty_secret_unknown_peer_rejected` | passed | `decision_code=api_auth_not_configured`<br>`http_status=503`<br>`route_reached=false` |
| `http_empty_secret_non_loopback_authority_rejected` | passed | `decision_code=local_authority_required`<br>`http_status=503`<br>`route_reached=false` |
| `http_empty_secret_forwarded_rejected` | passed | `decision_code=forwarded_request_rejected`<br>`http_status=503`<br>`route_reached=false` |
| `http_configured_secret_invalid_rejected` | passed | `decision_code=api_key_invalid`<br>`http_status=401`<br>`route_reached=false` |
| `http_configured_secret_valid_all_peers` | passed | `decision_code=allowed_api_key`<br>`loopback_route_reached=true`<br>`non_loopback_route_reached=true` |
| `websocket_header_credential_accepted` | passed | `decision_code=allowed_api_key`<br>`run_lookup_observed=true`<br>`connection_observed=true` |
| `websocket_query_credential_rejected` | passed | `decision_code=query_credential_rejected`<br>`close_code=1008`<br>`run_lookup_observed=false`<br>`connection_observed=false` |
| `websocket_invalid_origin_rejected` | passed | `decision_code=origin_not_allowed`<br>`close_code=1008`<br>`run_lookup_observed=false`<br>`connection_observed=false` |
| `cors_invalid_origin_rejected` | passed | `configuration_code=cors_origin_invalid`<br>`construction_rejected=true` |
| `cors_empty_secret_remote_origin_rejected` | passed | `configuration_code=cors_origin_requires_authenticated_runtime`<br>`construction_rejected=true` |
| `compose_loopback_required_secrets` | passed | `backend_host_ip=127.0.0.1`<br>`mysql_host_ip=127.0.0.1`<br>`api_secret_required=true`<br>`mysql_root_password_required=true`<br>`mysql_password_required=true`<br>`service_env_file_parameterized=true` |
| `container_health_privilege_contract` | passed | `backend_healthcheck_declared=true`<br>`mysql_healthcheck_declared=true`<br>`cap_drop_all_declared=true`<br>`no_new_privileges_declared=true`<br>`uvicorn_log_level=warning`<br>`container_runtime_scope=separate_required_lane` |

## Boundaries

- `source_loopback_access: proven`
- `authenticated_api_key_access: proven`
- `websocket_header_only_access: proven`
- `cors_exact_origin: proven`
- `container_configuration: proven`
- `container_runtime: separate_required_lane`
- `hosted_deployment: not_claimed`
- `live_provider_result: not_observed`

## Limits

- Deterministic local contract evidence, not a Docker runtime observation or deployment certification.
- TLS, identity, authorization, RBAC, and hosted operation are not proven.
- Provider, model, tool, and research quality are not observed.
- The required Docker runtime lane remains authoritative for container build, health, privilege inspection, and cleanup.
