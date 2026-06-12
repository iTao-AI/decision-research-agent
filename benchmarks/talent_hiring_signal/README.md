# Talent Hiring Signal Benchmark

This benchmark is the value gate for the `talent-hiring-signal` profile.

It intentionally contains no fabricated companies, job postings, findings, claims, or
scores. Populate the declared sample before running the profile.

## Required procedure

1. Select three target role directions and three to five relevant companies per role.
2. Record every public job posting or provided aggregate in `declared_samples`.
3. Run the existing `generic` profile and preserve its output as the baseline.
4. Manually label useful findings/claims and non-actionable filler.
5. Complete `north-star-decision-brief.template.json`.
6. Compare the Talent output on evidence coverage, scope adherence, limitations, and
   reviewability.

The P1A value gate passes only when at least three of the four dimensions improve.
Until then, Skills, Async Subagent, durable HITL, and UI expansion remain disabled.
