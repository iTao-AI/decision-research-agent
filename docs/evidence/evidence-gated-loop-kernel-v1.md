# Evidence-Gated Loop Kernel v1

This is provider-free offline verification of reviewed evidence-gated lineages.

## Record Status

- Record status: `valid`
- Cases: `3`; episodes: `4`

## Case Lineage Matrix

| Case | Episodes |
|---|---:|
| context-resolver-projection | 1 |
| evaluation-sensitivity | 1 |
| strict-citation-consumer | 2 |

## Evidence And Historical RED Boundary

Historical RED is reviewed provenance; it is not re-executed by this report.

## Fixed Verification Profiles

- `context-resolver-coherence@1`: `passed`
- `evaluation-sensitivity@1`: `passed`
- `strict-citation-consumer@1`: `passed`

## Candidate, Consumer, And Closure Axes

- Accepted candidates: `3`
- Closed no-change episodes: `1`

## Release Hold And Rollback

Release disposition: `hold`
Rollback is recommendation-only and is never executed by this kernel.

## Reproduce

```bash
PYTHON_DOTENV_DISABLED=1 python scripts/evidence_gated_loop_gate.py check
```

## Limits

- Maximum case bytes: `262144`

## Non-Claims

- No runtime self-modification, automatic diagnosis, candidate generation, promotion, release, or rollback.
- No live-provider success, production reliability, user-adoption, business-impact, or universal Agent-quality claim.
- Current fixed profiles verify retained repository state; they do not check out arbitrary historical candidates or infer human verdicts.
- The v0.1.6 selector verifies current release metadata only; it does not execute historical release behavior.
- Post-v0.1.6 capabilities are not part of the immutable v0.1.6 release.
- No live-provider strict success is claimed.
