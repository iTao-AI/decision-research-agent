# Fieldwork local authority and evidence

## Decision

Fieldwork is an opt-in, single-operator loopback workbench. Its SQLite state
owns project stage, material versions, proposals, approvals and export
metadata. A separate MKE library per project produces and serves Evidence. The
browser and model receive logical identifiers. The service supplies database
paths, original file paths and the MKE command arguments.

A verified MKE reference identifies the producing Run, Source, Publication
revision and Evidence ID. DRA records the consuming Run, source page range,
UTF-8 byte offsets, digest and text returned to the model. Chinese display
text uses the decoded string, with byte offsets explicitly labelled. A frozen
excerpt remains a snapshot even if the provider later retires the identity.
Live reread reports current availability separately.

Adoption is a DRA transaction. A pending replacement prevents confirmation;
after admission, the material and project revisions determine whether an
outstanding proposal is still current. Accepting the same proposal twice
returns the recorded state. Replacing a document keeps the old original and
frozen references. Independently confirmed investigation work survives failed
intake, analysis and approval.

The Fieldwork provider adapter makes one bounded proposal-generation call
with the admitted material and project state. It has no tools or write
authority. The general research Agent harness, public web evidence contract,
RAGFlow integrations and existing CLI/API authority stay in their established
paths. The opt-in workbench serves the same frontend build from a separate
loopback entry point with same-origin storage operations.

The standalone decision-html skill works from a confirmed snapshot. Local
operator registration verifies the identified snapshot fingerprint, then binds the HTML bytes and digest to that version. Serving uses a
sandboxed document and the registered file contains inert markup. The
snapshot and application record remain the source of the business decision.
