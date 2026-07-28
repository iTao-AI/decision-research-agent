# ADR: Evidence-Gated Evolution Authority

Status: Accepted

## Context

Reviewed failures and verification gaps need a durable provider-free lineage
without moving application truth or mutation authority into an evaluator.

## Decision

Place the Evidence-Gated Loop Kernel under Offline Verification. It consumes
reviewed public-safe records, executes a code-owned verification profile registry,
and records a human-reviewed verdict plus terminal episode release disposition.

## Authority Matrix

Application services own runtime state. Git identities own candidate history.
The kernel owns contract coherence. Human review owns diagnosis, carrier,
verdict, release, and rollback recommendation. Independent consumer checks own
consumer-owned proof.

## Candidate And Verifier Isolation

The candidate cannot modify its verifier, profile command, threshold, result,
or verdict. Manifest data cannot supply executable commands.

## Online Execution / Offline Verification

Online execution remains evidence-only. The privacy-safe observation is lossy
diagnostic input and not application truth.
It is not a fourth evolution-success case. Offline Verification validates
reviewed records and fixed profiles without runtime mutation.

## Release And Rollback

The terminal episode supplies the current case disposition. Release remains
separate human review; rollback is recommendation-only and never executes Git,
consumer pin, database, or runtime actions.

## Rejected Alternatives

Rejected alternatives include runtime self-modification, manifest-supplied
verification, hosted EvalOps authority, model-owned verdicts, multiple new
Agent roles, automatic release, and automatic rollback.

## Consequences

Candidate generation remains outside v1. New evidence or proof kinds require
adapter/profile and architecture review with a parallel versioned contract.

## Non-Claims

This ADR does not claim autonomous evolution, live-provider success,
production reliability, adoption, business impact, or publication.
