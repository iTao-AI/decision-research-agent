# Security Policy

Decision Research Agent v0.1.0 is a backend-and-CLI release. It ships the
FastAPI backend, Python Tool Client, operator scripts, tests, and documentation;
it does not ship a frontend service.

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

LangSmith traces are privacy-first by default. Keep inputs and outputs hidden
unless a local, low-sensitivity diagnostic task explicitly requires temporary
full trace visibility.

Treat uploaded content, model output, tool responses, external service
responses, generated reports, and persisted artifacts as untrusted input.

## Out Of Scope

- Public bug bounty commitments.
- Hosted service operations outside this repository.
- Future frontend, RBAC, multi-tenant, or multi-replica deployments that are not
  part of v0.1.0.
