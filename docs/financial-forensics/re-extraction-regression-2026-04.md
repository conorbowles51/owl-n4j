# Re-extraction is not improvement: what the ET-Fraud batches show

*Measured 2026-08-30 against `bundle/extraction-json/`, batches 2026-04-11
through 2026-04-18. Every figure below is reproducible from those files.*

## The short version

Nineteen documents in the corpus were extracted twice. All nineteen second
readings disagree with the first about the document's own control totals. Six
of them lost a balance identity that had previously closed to the cent, and
seventeen transaction rows went with it. One of them gained 375 rows and a
per-month validation that the first reading did not have.

Neither batch is better than the other. That is the finding, and it is the
empirical justification for a design decision already taken elsewhere in this
subsystem: when the same document is present twice, the copy that counts must
be chosen by evidence, and never by recency.

## What was measured

The corpus holds 326 extraction files covering 307 distinct documents. The
difference is 19 documents that were run through the pipeline more than once
and whose outputs were both kept.

For each of those 19, the earliest and latest readings were compared on two
things: the number of transaction rows extracted, and the verdict the balance
identity reaches on the document's printed control block
(`services.financial.statement_totals.infer_convention`).

| Transition (earliest → latest) | Count |
| --- | --- |
| `not-testable` → `not-testable` | 11 |
| `magnitude` → `not-testable` | 6 |
| `magnitude` → `magnitude` | 2 |

`header_totals` differs between the two readings in 19 cases out of 19. Not one
re-extraction reproduced the control block it replaced.

## The six that lost their check

| Document | Batches | Control keys | Rows | Earlier delta |
| --- | --- | --- | --- | --- |
| USA-ET-000388 | 04-11 → 04-12 | 9 → 1 | 62 → 56 | 0.00 USD |
| USA-ET-000396 | 04-11 → 04-12 | 9 → 1 | 138 → 130 | 0.00 USD |
| USA-ET-000450 | 04-11 → 04-12 | 9 → 1 | 100 → 100 | 0.00 USD |
| USA-ET-000478 | 04-11 → 04-12 | 9 → 1 | 108 → 105 | 0.00 USD |
| USA-ET-001085 | 04-11 → 04-12 | 6 → 1 | 55 → 55 | 0.00 USD |
| USA-ET-007020 | 04-11 → 04-12 | 9 → 1 | 162 → 162 | 0.00 USD |

All six first readings balanced exactly. Not approximately: the opening
balance plus the printed inflows less the printed outflows equalled the printed
closing balance to the cent, on all six.

All six second readings used `pdfplumber line-by-line with category mapping`
and replaced the entire control block with a single free-text note. For
USA-ET-000388 the replacement is, in full:

```json
{"notes": "56 txns, pdfplumber extraction"}
```

The note is not a control total. It is the extractor's own row count, restated,
which can only ever agree with itself. What it displaced was six or nine
figures the bank computed.

Across those six documents the later reading holds 17 fewer transaction rows
than the earlier one. Three of the six lost rows; the other three kept their row
count and lost the block anyway, which is worth stating plainly because it means
row count is not a proxy for extraction quality. A pass can preserve every row
and still leave the document unprovable.

This is the exact failure the financial subsystem exists to catch, occurring in
the corpus it was built from. Rows went missing, and the one artefact capable of
proving they had gone missing was destroyed in the same pass. A dropped row
produces no low-confidence signal — the extractor is not uncertain about a line
it never saw — so the arithmetic is the only detector, and here the arithmetic
was removed along with the evidence. Had the second batch simply overwritten the
first, the loss would have been undetectable and permanent.

## The one that improved

USA-ET-026407 went the other way, and by a wide margin.

The 2026-04-12 reading carries 16 rows, a statement period recorded as
`{"from": "varies", "to": "varies"}`, and this control block:

```json
{"notes": "Restored from Neo4j v2 nodes (16 txns)"}
```

Its `extraction_method` is `Restored from Neo4j after accidental overwrite` —
so that reading is itself the residue of an earlier data-loss event, recovered
from the graph rather than from the document.

The 2026-04-17 reading carries 391 rows, a real period of 2020-12-07 to
2021-05-06, and a structured block declaring `statements_in_document: 12`,
total additions of $109,614.07 and total subtractions of $102,694.71, with a
`by_month` breakdown that validates the extracted rows against each month's own
printed additions and subtractions figures. All five validated months agree
exactly.

Two caveats belong with that, because the improvement is real but narrower than
it looks. The block declares twelve statements and itemises five, so seven are
unaccounted for. And every one of the five carries `ending_balance: null`,
which is why this document is still `not-testable` under the balance identity
despite the far better extraction: the identity needs a closing balance and no
closing balance was captured. A per-month additions-and-subtractions check and
the opening-to-closing balance identity are independent checks, and passing one
says nothing about the other.

## What follows from it

**A primary is chosen by evidence, never by recency.** Latest-wins is the
obvious rule and it is wrong here in six documented cases. Byte-recency
correlates with nothing that matters. The properties that do matter are
observable and already recorded per document: does the control block survive,
does the identity close, how many rows were recovered, and by what extraction
layer. Nomination reads those.

**Superseding a document is not deleting it.** The six regressed readings must
remain retrievable, because the argument that they are regressions is made *by
comparing them against the copies they would have replaced*. This is what
`LedgerStatus.superseded` is for, and it is why the duplicate machinery excludes
rather than deletes. A pipeline that had cleaned up after itself would have
destroyed the evidence for its own defect.

**A control block may not be overwritten by a weaker one.** Nine bank-computed
figures replaced by a restatement of our own row count is a strict loss of
information, whatever else the pass improved. Where a later reading cannot
recover the block, the block from the earlier reading stands and the later rows
are checked against it.

**Rung 2 of the duplicate cascade stays advisory.** These pairs match at
`DuplicateMatchRung.same_account_period` — same account, same dates, different
content — which is exactly the rung documented as a candidate rather than a
finding. Acting on it automatically would have discarded a real reading in
either direction. It is raised for a person.

**Extraction method belongs on the record.** Each of these files states how it
was produced, and the method is what explains the pattern: every regression is
`pdfplumber line-by-line with category mapping`, and the two documents that kept
their identity across re-extraction are the two produced by `pdfplumber text +
line-walk + direction classifier + subtotal validation`. The method is not
metadata trivia; it predicts the outcome.

## Reproducing this

The measurement compares, for each document appearing in more than one batch,
the earliest and latest files by batch date, skipping `_audit_summary.json`,
`_queue.json`, `_archive_2026-04-17_pypdf_bad/` and `_ocr_cache/`. Verdicts come
from `infer_convention(header_totals, currency="USD")`: `not-testable` where the
block lacks both balances or all flow figures, otherwise the dialect that closes
if exactly one does.

No case content is reproduced here beyond document identifiers, the control
figures needed to state the finding, and arithmetic over them.
