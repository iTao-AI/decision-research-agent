# Fieldwork fictional test materials

The three PDF files share the visible title 试点安排确认函 and the
portable filename `pilot-arrangement-letter.pdf`. Each has a selectable
Chinese text layer on page 1. Use a fresh project for independent cases. To
exercise replacement, upload B with A selected as the document it replaces.

| Case | Starting state | What the proposal should support |
|---|---|---|
| A | The sample still needs preparation. | Prioritize preparing the anonymized export sample for Wednesday's customer demo. Keep live reading pending separate customer IT approval. Continue interviews and equipment version checks. |
| B | The letter replaces A or is the only applicable letter. | Allow internal rehearsal with the anonymized export sample. Keep customer-facing sample use pending separate written authorization and live reading pending approval. Continue interviews. |
| C | The letter is the only applicable letter. | Treat receipt of the application as acknowledgement. Ask customer IT whether the sample may be shown, to whom, and within what data scope. Continue interviews. |
| A, sample prepared | Use the exact A PDF and record sample preparation before analyzing. | Take a distinct next step, such as checking the prepared sample and demo plan. Keep the conditions for live reading and interviews. |
| A, then B | Save A's proposal, register B as its replacement, then submit the stale approval. | Reject the stale approval and keep A's original evidence readable. Preserve the last confirmed arrangements and independent investigation. |

Assess recommended actions and conditions alongside their exact page 1 excerpts.
A source match alone only establishes the quoted text. Confirm that the passage
supports the action for the intended audience and that the model or replay saw it.

`frozen-readback.json` is keyed by PDF SHA-256 and contains the complete text
from local MKE `evidence read` for each PDF. Each read was complete at byte offset
zero, matched the scoped browse identity and text, and matched the reported UTF-8
length and SHA-256. The bundled readback is for the explicit local replay mode.
The acceptance table is for review.

To rebuild the PDFs with PyMuPDF, use a scratch destination.

```shell
python examples/fieldwork/generate_fixtures.py --output-dir output/fieldwork/rebuilt-fixtures
```

The PDF serializer can vary across PyMuPDF versions. Use the tracked PDFs for
replay. When intentionally changing a fixture, ingest it into a disposable local
MKE library, verify the catalog's run and file fingerprint, browse the corresponding
Source and Publication, and freeze the complete page 1 evidence returned by
`evidence read` under the new file fingerprint.
