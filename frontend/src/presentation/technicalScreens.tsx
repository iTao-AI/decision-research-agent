import { type ConsoleProjection } from "../consoleProjection";
import { copy, type Language } from "../i18n";
import {
  countSummary,
  KeyValueList,
  ObservationSection,
  ObservationValue
} from "./observation";

export function Metric({ label, value, tone }: { label: string; value: string; tone: string }) {
  return (
    <article className={`metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

export function CommandCenter({
  language,
  projection
}: {
  language: Language;
  projection: ConsoleProjection;
}) {
  const t = copy[language];
  return (
    <div className="command-grid">
      <div className="flow-map">
        <div className="caller-row">
          {["OpenClaw", "Codex", "Tool Client", "REST caller"].map((caller) => (
            <span className="caller" key={caller}>
              {caller}
            </span>
          ))}
        </div>
        <span className="flow-connector" aria-hidden="true">↓</span>
        <div className="execution-path">
          <span className="node">FastAPI</span>
          <span className="arrow">→</span>
          <span className="node">ResearchExecutionService</span>
          <span className="arrow">→</span>
          <span className="node">DeepAgentsHarness</span>
        </div>
        <div className="authority-row">
          <span className="flow-connector" aria-hidden="true">↳</span>
          <span className="node authority">Application DB authority</span>
        </div>
        <p className="note">
          {t.labels.authority}: Application DB = business authority; LangSmith = diagnostics only.
        </p>
      </div>

      <div className="projection-stack">
        <h3>{projection.source === "static" ? t.projection.staticSnapshot : t.projection.liveProjection}</h3>
        <ObservationSection
          language={language}
          observation={projection.command.create}
          title={t.projection.createReceipt}
          render={(receipt) => (
            <KeyValueList
              entries={[
                ["run_id", receipt.runId],
                ["thread_id", receipt.threadId],
                ["segment_id", receipt.segmentId],
                ["status", receipt.status],
                ["idempotent_replay", String(receipt.idempotentReplay)]
              ]}
            />
          )}
        />
        <ObservationSection
          language={language}
          observation={projection.command.run}
          title={t.projection.runState}
          render={(run) => (
            <KeyValueList
              entries={[
                ["run_id", run.runId],
                ["thread_id", run.threadId],
                ["profile_id", run.profileId],
                ["state_version", String(run.stateVersion)],
                ["execution_status", <ObservationValue language={language} observation={run.executionStatus} />],
                ["review_status", <ObservationValue language={language} observation={run.reviewStatus} />],
                ["delivery_status", <ObservationValue language={language} observation={run.deliveryStatus} />]
              ]}
            />
          )}
        />
        <ObservationSection
          language={language}
          observation={projection.command.publication}
          title={t.projection.publication}
          render={(publication) => (
            <KeyValueList
              entries={[
                ["publication_id", publication.publicationId],
                ["revision", String(publication.revision)],
                ["status", publication.status],
                ["artifact_ids", publication.artifactIds.join(", ") || t.observations.observedEmptyCollection]
              ]}
            />
          )}
        />
        <ObservationSection
          language={language}
          observation={projection.command.artifacts}
          title={t.projection.artifacts}
          render={(artifacts) =>
            artifacts.length === 0 ? (
              <p className="observation observed-empty">{t.observations.observedEmptyCollection}</p>
            ) : (
              <ul className="projection-list">
                {artifacts.map((artifact) => (
                  <li key={artifact.artifactId}>
                    <strong>{artifact.artifactId}</strong>
                    <span>{artifact.mediaType}</span>
                    <code>{artifact.contentHash}</code>
                  </li>
                ))}
              </ul>
            )
          }
        />
      </div>
    </div>
  );
}

export function RunLifecycle({
  language,
  projection
}: {
  language: Language;
  projection: ConsoleProjection;
}) {
  const t = copy[language];
  const lifecycle = projection.lifecycle;
  return (
    <div className="two-column">
      <section>
        <h3>{lifecycle.kind === "event_history" ? t.projection.eventHistory : t.projection.stateProjection}</h3>
        {lifecycle.entries.kind === "observed" ? (
          lifecycle.entries.value.length === 0 ? (
            <p className="observation observed-empty">{t.observations.observedEmptyCollection}</p>
          ) : (
            <ol className="run-spine">
              {lifecycle.entries.value.map((entry, index) => (
                <li key={`${entry.category}-${entry.label}-${index}`}>
                  <strong>{entry.label}</strong>
                  {entry.segmentKind && <span>{entry.segmentKind}</span>}
                  <span>
                    status: <ObservationValue language={language} observation={entry.status} />
                  </span>
                  <span>
                    sequence: <ObservationValue language={language} observation={entry.sequence} />
                  </span>
                  <span>
                    attempt: <ObservationValue language={language} observation={entry.attempt} />
                  </span>
                </li>
              ))}
            </ol>
          )
        ) : (
          <ObservationValue language={language} observation={lifecycle.entries} />
        )}
      </section>
      <ObservationSection
        language={language}
        observation={lifecycle.failureCause}
        title={t.projection.failureCause}
        render={(failureCause) => (
          <KeyValueList
            entries={[
              ["schema_version", failureCause.schemaVersion],
              ["phase", failureCause.phase],
              ["code", failureCause.code],
              ["recorded_at", failureCause.recordedAt]
            ]}
          />
        )}
      />
    </div>
  );
}

export function EvidenceLedger({
  language,
  projection
}: {
  language: Language;
  projection: ConsoleProjection;
}) {
  const t = copy[language];
  if (projection.evidence.kind !== "observed") {
    return (
      <article className="observation-card">
        <ObservationValue language={language} observation={projection.evidence} />
      </article>
    );
  }
  if (projection.evidence.value.length === 0) {
    return <p className="observation observed-empty">{t.observations.observedEmptyEvidence}</p>;
  }
  return (
    <div className="evidence-grid">
      {projection.evidence.value.map((entry) => (
        <article className="evidence-card" key={entry.evidenceId}>
          <header>
            <strong>{entry.evidenceId}</strong>
            <span>{entry.verificationStatus}</span>
          </header>
          <p>{entry.sourceIdentity}</p>
          <p>
            source_url: <ObservationValue language={language} observation={entry.sourceUrl} />
          </p>
          <p>
            citation_status: <ObservationValue language={language} observation={entry.citationStatus} />
          </p>
          <code>{entry.fingerprint}</code>
          {entry.citedBy.kind === "observed" && (
            <div className="chips" aria-label={t.labels.citedBy}>
              {entry.citedBy.value.map((claim) => (
                <span key={claim}>{claim}</span>
              ))}
            </div>
          )}
        </article>
      ))}
    </div>
  );
}

export function ReviewVerification({
  language,
  projection
}: {
  language: Language;
  projection: ConsoleProjection;
}) {
  const t = copy[language];
  const review = projection.review;
  return (
    <div className="two-column">
      <div className="projection-stack">
        <article className="ledger-card">
          <h3>{t.labels.review}</h3>
          <KeyValueList
            entries={[
              ["status", <ObservationValue language={language} observation={review.status} />],
              ["decision_id", <ObservationValue language={language} observation={review.decisionId} />],
              ["state_version", <ObservationValue language={language} observation={review.stateVersion} />],
              ["idempotency", <ObservationValue language={language} observation={review.idempotency} />]
            ]}
          />
        </article>
        <ObservationSection
          language={language}
          observation={review.workflow}
          title={t.projection.workflow}
          render={(workflow) => (
            <KeyValueList
              entries={[
                ["workflow_id", workflow.workflow_id],
                ["review_id", workflow.review_id],
                ["status", workflow.status],
                ["decision_id", workflow.decision_id ?? t.observations.notApplicable]
              ]}
            />
          )}
        />
        <ObservationSection
          language={language}
          observation={review.decision}
          title={t.projection.decision}
          render={(decision) => (
            <KeyValueList
              entries={[
                ["decision_id", decision.decision_id],
                ["review_id", decision.review_id],
                ["action", decision.action],
                ["accepted_state_version", String(decision.accepted_state_version)]
              ]}
            />
          )}
        />
        <ObservationSection
          language={language}
          observation={review.resolution}
          title={t.projection.resolution}
          render={(resolution) => (
            <KeyValueList
              entries={[
                ["resolution_id", resolution.resolution_id],
                ["decision_id", resolution.decision_id],
                ["action", resolution.action],
                ["artifact_ids", resolution.artifact_ids.join(", ") || t.observations.observedEmptyCollection]
              ]}
            />
          )}
        />
      </div>
      <ObservationSection
        language={language}
        observation={projection.verification}
        title={t.labels.verification}
        render={(verification) =>
          verification.source === "static" ? (
            <KeyValueList
              entries={[
                ["snapshot", verification.snapshot],
                ["origin", verification.baselineOrigin],
                ["status", verification.status],
                ["publication", verification.publicationFreshness]
              ]}
            />
          ) : (
            <KeyValueList
              entries={[
                ["state_counts", countSummary(verification.stateCounts)],
                ["origin_counts", countSummary(verification.originCounts)],
                ["snapshot_hash", verification.snapshotHash ?? t.observations.notApplicable]
              ]}
            />
          )
        }
      />
    </div>
  );
}

export function CanonicalResult({
  language,
  projection
}: {
  language: Language;
  projection: ConsoleProjection;
}) {
  const t = copy[language];
  if (projection.result.kind === "observed") {
    const result = projection.result.value;
    return (
      <div className="result-layout">
        <article className="ledger-card">
          <h3>{t.labels.artifact}</h3>
          <KeyValueList
            entries={[
              ["run_id", result.runId],
              ["artifact_id", result.artifact.artifactId],
              ["kind", <ObservationValue language={language} observation={result.artifact.kind} />],
              ["media_type", result.artifact.mediaType],
              ["content_hash", result.artifact.contentHash],
              ["revision", <ObservationValue language={language} observation={result.artifact.revision} />],
              ["safety", <ObservationValue language={language} observation={result.artifact.safety} />]
            ]}
          />
        </article>
        <article className="markdown-preview">
          <pre>{result.artifact.content}</pre>
        </article>
      </div>
    );
  }
  if (projection.result.kind === "not_applicable") {
    return (
      <article className="ledger-card terminal-card">
        <h3>{t.observations.terminalNoResult}</h3>
        {projection.lifecycle.run.kind === "observed" && (
          <KeyValueList
            entries={[
              ["run_id", projection.lifecycle.run.value.runId],
              [
                "execution_status",
                <ObservationValue
                  language={language}
                  observation={projection.lifecycle.run.value.executionStatus}
                />
              ],
              [
                "delivery_status",
                <ObservationValue
                  language={language}
                  observation={projection.lifecycle.run.value.deliveryStatus}
                />
              ]
            ]}
          />
        )}
      </article>
    );
  }
  return (
    <article className="observation-card">
      <ObservationValue language={language} observation={projection.result} />
    </article>
  );
}

export function ArchitectureMode({
  language,
  projection
}: {
  language: Language;
  projection: ConsoleProjection;
}) {
  const t = copy[language];
  return (
    <div>
      <h3>{t.labels.authority}</h3>
      <p className="observation unsupported">{t.observations.referenceOnly}</p>
      <ol className="architecture-flow">
        {projection.architecture.nodes.map((node) => (
          <li key={node}>{node}</li>
        ))}
      </ol>
    </div>
  );
}
