# Frozen source provenance

The corpus pairs authored findings with bounded, frozen passages. Its 18
statement rows are synthetic controls, including the holdout rows based on
independent project documentation. The authored verdicts exercise the scoring
logic. The eight blind-review candidates have pending human judgments.

Offsets count Python Unicode code points in the frozen snippet, starting
at zero and excluding the end. The intentionally damaged reference in
`delivery-owner-broken-reference` exercises the structural-error path.
The corpus and the demo can be read offline from the files in this directory.

## Development

- `delivery-authority` uses the frozen DRA decision from
  `8b884a2f2e4cebbe43decc35d1e7ac1b4e9caca1`, lines 16–22 and 66–73.
  The SHA-256 of the source file is
  `710a085f2b63c963b53c7bd9a02c1d5b185b800cc4ae4ff1a499315e15c140ad`.
  [Delivery authority](https://github.com/iTao-AI/decision-research-agent/blob/8b884a2f2e4cebbe43decc35d1e7ac1b4e9caca1/docs/decisions/research-findings-delivery-authority.md)
- `benchmark-value` uses the DRA project instructions at the same commit,
  lines 25–27. The SHA-256 of the source file is
  `0dd5deaf48dbd5ad45364e98c6aec48321a60f685f5561d80938cb601bc7671d`.
  [Project instructions](https://github.com/iTao-AI/decision-research-agent/blob/8b884a2f2e4cebbe43decc35d1e7ac1b4e9caca1/AGENTS.md)
- `policy-conflict` reuses the pilot's two fictional procurement memos.
  The example.com URLs are stable fixture identifiers for the bundled text.
  Each memo concerns the same pilot and leaves its authority and effective
  date unspecified.

The pilot material was checked in local Git at
`aada77bc95809d9c240f206a062b9b3ee978cc3a` under
`tests/fixtures/research-quality-pilot/`. The pilot `cases.json` supplies
question text, `sources.json` supplies extracts and hashes, `gold.json`
records preregistered expectations, and `scripted-candidates.json` supplies
the original inverted statements and citations in
`control-entailment-flip` and `control-human-value`. The extracts from both repository
files were compared with the specified lines after whitespace normalization,
and both source-file and frozen-text SHA-256 values were verified against
the pilot manifest. DRA material is distributed under the repository's
[MIT license](../../LICENSE).

## Holdout

These snapshots were checked on 2026-11-19. The URLs use the commit
resolved from each release tag. The passages are short authored factual
extracts of the identified documentation sections. The snippets and
offsets describe those extracts.

- `uv-lock-and-sync` uses uv 0.9.9 documentation, lines 14–50 and 92–101.
  The SHA-256 of the pinned Markdown file is
  `1c00e8eb6084bebc206fb2e2cb3e4a72b51e20ca455fa67b54d923641b64ab05`.
  uv offers the MIT license as one of its licensing options.
  [Locking and syncing](https://github.com/astral-sh/uv/blob/4fac4cb7ed8679debac7e495824367bf9abfeea8/docs/concepts/projects/sync.md)
  [License terms](https://github.com/astral-sh/uv/blob/4fac4cb7ed8679debac7e495824367bf9abfeea8/README.md#license)
  [MIT license](https://github.com/astral-sh/uv/blob/4fac4cb7ed8679debac7e495824367bf9abfeea8/LICENSE-MIT)
- `ruff-configuration` uses Ruff 0.14.6 documentation, lines 255–282.
  The SHA-256 of the pinned Markdown file is
  `1c7e80048d5fcc373900d330ff8730a7309303f4ecc9bdab967c6b4dac88d3a3`.
  Ruff's configuration documentation is in its MIT-licensed repository.
  [Config file discovery](https://github.com/astral-sh/ruff/blob/59c6cb521d26380120f8522476fd09d296bf4f2e/docs/configuration.md#L255-L282)
  [MIT license](https://github.com/astral-sh/ruff/blob/59c6cb521d26380120f8522476fd09d296bf4f2e/LICENSE)

Each source and task family stays within one split, including corrected and
flipped statements. Retire a holdout family from future held-out comparisons
if its examples are used to tune a prompt or evaluator.

## Historical evidence and demo

[Historical pointers](historical.json) retain dated investigations as leads.
None supplies a delivered finding with its exact bound citations for replay.
The pilot's preregistered expectations carry no completed independent human
judgment of generated output.

[Demo delivery](demo-delivery.json) is a synthetic package using the exact
statement and reference from `control-entailment-flip`. The existing
findings consumer validates its own-byte artifact hash, same-run binding,
and excerpt offsets. Use `--origin synthetic_control` when exercising intake
with this package.
