# Chinese research report quality v1

## Public citation replay

From the repository root, with the project dependencies installed, run this command.

```sh
python scripts/chinese_report_quality.py public-citation-replay
```

The command reads the [tracked fixture](public-citation-replay.json) and writes
`output/chinese-report-quality-v1/public-citation-replay.json`. It uses the
application's structured delivery binder and fixed manual semantic labels tied
to the review input fingerprints. The replay runs locally with the two frozen
official excerpts.

Both cases ask the same question about a bot proactively sending to a group.
They use the same Chinese conclusion and vary only the cited source. The
[send-message document](https://open.feishu.cn/document/server-docs/im-v1/message/create.md)
supports the conclusion for `POST /open-apis/im/v1/messages`. The
[reply-message document](https://open.feishu.cn/document/server-docs/im-v1/message/reply.md)
has a similar one-hour rule for `POST /open-apis/im/v1/messages/:message_id/reply`.
Both excerpts bind exactly. The fixed source-support verdict is `supported`
for the send citation and `insufficient_evidence` for the reply citation.

The result records each claim, the official quote and its operation, the
binding outcome, and the reason for the fixed verdict. The fixture records
the frozen source dates, body hashes and line locators. The scope is citation
binding and operation-specific support on this pair.

## Retained development and historical evaluation

The development set has [four questions and five material conditions](dev-cases.json).
Zotero tests generic Markdown. GitHub release download counts and the
LangGraph/Feishu case test evidence research. The troubleshooting case has
two material conditions. Only the complete condition includes the approval
example. Both conditions require internal authorization evidence for the
team’s actual permissions.

[Source manifest](source-manifest.json) identifies the versions, locators and
hashes of the development material. Local evaluation uses a paired `cases.json`
and `sources.json` in a material directory. The source packet restores
each original `snippet` and `excerpt`. The four development questions and
source locators are tracked. Their source packet, generated candidates, and
judgment receipts require the retained local materials. The historical replay
also requires the original local archive. A current fetch from a rolling
documentation page can differ from the frozen snapshot. The dates and employer
snapshots in the calendar and Talent holdout inputs are separate from this
development set.

## Replay

With `MATERIAL_DIR` set to the retained material directory and `REPLAY_DIR`
set to an output directory, prepare the frozen model input:

```sh
python scripts/chinese_report_quality.py prepare \
  --material-dir "$MATERIAL_DIR" --source-manifest benchmarks/chinese-report-quality-v1/source-manifest.json \
  --output "$REPLAY_DIR/generator-input.json"
```

Use the same generator model, settings, questions and packet in a comparison.
Keep disjoint material conditions in isolated generation contexts. Retain the
candidate output separately from the inputs. In the controlled generic Markdown
format, use plain inline markers such as `[1]` for the corresponding
one-based entry in the candidate's `citations` array. Run the application’s binder:

```sh
python scripts/chinese_report_quality.py bind \
  --material-dir "$MATERIAL_DIR" --source-manifest benchmarks/chinese-report-quality-v1/source-manifest.json \
  --generator-input "$REPLAY_DIR/generator-input.json" \
  --candidates "$REPLAY_DIR/generator-output.json" --output-dir "$REPLAY_DIR"
```

Give independent reviewers only the `input_sha256` and `input` of the records
in `judge-input.json`. Keep the experiment arm, case envelope and model
identity out of their inputs. [The existing findings evaluator](../findings-quality-v1/README.md)
defines source-support verdicts. Also score required coverage, Chinese
readability and applicable critical errors. Validate a returned judgment
against the same input:

```sh
python scripts/chinese_report_quality.py record \
  --blind-input "$REPLAY_DIR/judge-input.json" --judgments "$REPLAY_DIR/judge-output.json" \
  --output "$REPLAY_DIR/recorded-judgments.json"
```

For the retained execution-only Python 3.13 run, set `ARCHIVE_DIR` to the
directory holding its status, terminal API responses, diagnostic artifact,
tool events and binding probes. Replay the actual ledger:

```sh
python scripts/chinese_report_quality.py history --archive "$ARCHIVE_DIR" --output-dir "$REPLAY_DIR"
python scripts/findings_quality.py replay --dataset benchmarks/findings-quality-v1 \
  --observation "$REPLAY_DIR/observation.json" --output-dir "$REPLAY_DIR/english-regression"
```

Structural checks report exact binding and per-source attribution. Generic
Markdown locator checks are secondary observations. The standard generic
product path has its own delivery and does not enforce this structured
binding contract. Model judgments measure source support, coverage and
readability for the delivered or controlled artifact under review. Label
provider runs, fixture replays and managed-model judgments separately. When a
run produced no report, record its earliest observed deviation and leave
semantic scoring unavailable. Talent runs use their separate
[scope and DecisionBrief contract](../talent-hiring-signal-v1/README.md).
