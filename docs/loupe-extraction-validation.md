# Extraction measurement and regression checks

The offline runner measures supplied extraction results against reviewed ground
truth. It does not call an AI provider, extract a PDF, create labels, or certify
that the labels are correct. This is separate from the existing control-block
corpus census in `backend/services/financial/corpus.py`.

Run from the repository root with the local backend virtual environment:

```sh
PYTHON_DOTENV_DISABLED=1 data/local-runtime/backend-venv/bin/python scripts/evaluate_financial_extraction.py corpus-run.json --output measurements.json
```

To compare against an earlier run:

```sh
PYTHON_DOTENV_DISABLED=1 data/local-runtime/backend-venv/bin/python scripts/evaluate_financial_extraction.py current-run.json --baseline previous-run.json --output comparison.json
```

Output files must not already exist. A measured regression writes the report and
returns exit code 2. Invalid/incomparable inputs fail instead of reporting a pass.
Changing reviewed ground truth requires a new baseline. Measurements retain integer
numerators and denominators; zero-denominator rates are unavailable, not zero.

The input schema is `ExtractionEvaluation` in
`backend/services/financial/extraction_evaluation.py`. Its top-level fields are:

- `schema_version`: `loupe.extraction_evaluation/1`.
- `corpus_id`, `corpus_version`: stable identifiers for the reviewed corpus.
- `reviewer_ids`: at least two distinct identifiers; these are declarations,
  not proof of reviewer independence.
- `adjudication_reference`: the record resolving label disagreements.
- `label_status`: `synthetic_test` or `independently_reviewed`.
- `documents`: source SHA-256, extraction layer/version, proof class, recorded
  balance-gate outcome, quarantine state, truth rows and predicted rows.

Every row has a stable `source_id` shared by truth and prediction for that source
position. Fields are exact strings keyed by `date`, `amount_minor`, `currency`,
`direction`, and `account`. Use canonical reviewed representations in both runs;
there is no fuzzy matching, money conversion or date inference. Each predicted
row also declares `admitted`. Omitted expected fields count as missing. Extra
predicted fields, differing values, and invented rows count as errors if admitted.
A stable source row identity is essential: the runner cannot discover or repair
incorrect alignment between truth and predictions.

Reports cover row recall/precision, field recall/precision, direction accuracy,
errors among admitted readings, quarantine rate, and available balance-gate pass
rates by proof class. Regression checks compare accuracy and admitted-error rates.
Balance pass/quarantine rates are reported separately: increasing or decreasing
them does not by itself establish an improvement.

Remaining acceptance work:

- [x] Offline schema validation, exact measurements and regression comparison.
- [x] Synthetic missed-row, invented-row, wrong-direction, missing-field,
  unavailable-rate and changed-ground-truth checks.
- [x] Reconcile two source-bound reader records, record explicit disagreement
  resolutions, and bind the resulting labels to separate extraction outputs.
  Unresolved reviews never produce a partial truth set. See the workflow below.
- [ ] Establish independently reviewed labels across representative institutions,
  layouts and difficult scans, with disagreements recorded.
- [ ] Capture actual extraction outputs against those labels and publish the
  versioned measured report. A working provider is needed for model-layer runs.
- [ ] Wire the approved private corpus into the release regression gate. The
  original evidence and labels must remain in their authorized storage.

The readable ledger methods appendix explicitly reports that an accuracy report
is not included. Do not replace that statement until a versioned report is actually
captured and tied to the extraction versions in the export. The appendix is not yet
all of the original specification's expert packet or complete case custody history.

## Two-reader reference workflow

The repository's larger private corpus is present: 326 active extraction files.
Forty contain a `validation` object, but those fields are extraction/control checks,
not independent reader labels. No explicit ground-truth/reviewer/adjudication fields
were found at their top level. These files must not be relabelled as independent
ground truth merely because they have been used before.

Each reader supplies an `extraction_reader_review/1` record independently from the
original sources. The record identifies the corpus/version, reader and review IDs,
source-file SHA-256, whether the complete source was reviewed, and exact labelled
rows. Both readers must cover the same source inventory. Row IDs must identify
stable positions in the original document, not an assumed agreement with whatever
row numbers a new extractor happens to emit. No row alignment is inferred.

This minimal example is **synthetic**, not a reviewed real source:

```json
{
  "schema_version": "loupe.extraction_reader_review/1",
  "corpus_id": "synthetic-example",
  "corpus_version": "1",
  "review_id": "reader-a-run-1",
  "reviewer_id": "reader-a",
  "label_status": "synthetic_test",
  "documents": [{
    "source_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "complete_source_reviewed": true,
    "rows": [{
      "source_id": "page-1/printed-row-1",
      "fields": {"amount_minor": "1234", "currency": "GBP", "direction": "debit"}
    }]
  }]
}
```

Real independently produced reviews use `label_status: "independent_reader"`.
Identity, independence, complete coverage and correctness remain reader declarations;
the tool does not authenticate them. Two matching readers can still both be wrong.
Do not create two nominal reader files from one automated extraction and describe
that as independent review.

Compare the two records:

```sh
data/local-runtime/backend-venv/bin/python scripts/reconcile_financial_reference_reviews.py \
  reader-a.json reader-b.json --output review-comparison.json
```

Exit 2 means disagreements remain. The report retains both inputs and their digests,
and lists differing field values or row presence. It emits **no truth documents**
until every disagreement is resolved. No source PDF or model is read by the tool.

An adjudication uses schema `loupe.extraction_review_adjudication/1`, a recorded
`adjudication_id` and `adjudicator_id`, the exact `first_review_sha256` and
`second_review_sha256` from the comparison, and a `resolutions` list. Each resolution
contains `source_sha256`, `source_id`, `final_fields` and a nonblank `reason`.
`final_fields: null` explicitly excludes that disputed row. Duplicate resolutions,
changes to agreed rows, and references to changed reader versions are refused.
Rerun the command with `--adjudication resolutions.json` and a new output path.

Supply extraction output separately as `loupe.extraction_predictions/1`, containing
only `schema_version`, `corpus_id`, `corpus_version` and `documents`. Each document
has the existing evaluation metadata and `predictions` fields described above,
but **no `truth`**. Its source inventory must exactly match the reconciled reviews.

```sh
data/local-runtime/backend-venv/bin/python scripts/evaluate_financial_extraction.py \
  predictions.json --review-record reconciled-reviews.json \
  --output measurements.json --prepared-corpus prepared-corpus.json
```

The measurement reruns review reconciliation and rejects changed truth, even if an
edited record supplies a new hash. It preserves the review-record digest in the
measurement. The optional prepared corpus can be retained with an expert-support
bundle using the existing `--validation-corpus` option. Synthetic labels remain
synthetic throughout. Output paths must be new and distinct.

With `--review-record`, an optional `--baseline` also contains predictions in that
schema: both prediction sets are measured against the selected reviewed labels.
Retain the resulting versioned baseline and review record; do not present this as
reuse of an old accuracy result if the ground truth changed.


### Retain review evidence with selected tracing support

The offline assembler now accepts the reconciled record and predictions directly:

```sh
data/local-runtime/backend-venv/bin/python scripts/assemble_financial_trace_support.py \
  selected-scenario.json --reference-review reconciled-review.json \
  --validation-predictions predictions.json --output new-support.zip
```

It reruns reconciliation, assembles truth from the retained reader/adjudication
records and recalculates measurements. It retains the original review values,
predictions, prepared corpus and measurement report as hash-listed ZIP members.
Do not also pass `--validation-corpus`; the two input modes are mutually exclusive.
Each selected scenario's expert index links the validation and compares its recorded
ledger source hashes to the corpus. Missing digests and unmeasured sources are
explicit. Pending documents outside those ledger readings are outside the overlap
check. Matching source bytes do not establish matching extraction versions/settings
or review workflows. Synthetic reviews stay synthetic, and reviewer independence
remains a supplied declaration. No model call, database write or external upload.


Add `--ledger-export saved-ledger.zip` to retain a verified original ledger ZIP in
the same support bundle. It must belong to the scenarios' case. The assembler
checks all declared members and recomputes an included audit chain. It preserves
the ZIP exactly and records whether wider case history was selected. That ledger
capture remains separate from each scenario's snapshot; the bundle does not merge
their rows or claim that their dates and filters match.

### Release regression command

The standalone release check is ready for an approved private corpus location:

```sh
data/local-runtime/backend-venv/bin/python scripts/check_financial_extraction_release.py \
  --review-record reconciled-review.json --expected-review-sha256 REVIEW_RECORD_DIGEST \
  --baseline baseline-predictions.json --expected-baseline-sha256 BASELINE_FILE_DIGEST \
  --current current-predictions.json --output new-release-check.json
```

The review pin is the reconciliation record's `review_record_sha256`; the baseline
pin is SHA-256 of the exact baseline file bytes. Retain pins separately during
release review, rather than deriving them automatically from whatever input is
being tested. The command recomputes reconciliation, binds both runs to the same
truth, refuses synthetic labels or sources without reviewed transaction rows and
returns exit2 with a report on a measured regression. Invalid or mismatched inputs
fail without a success report. Output is a new file; no database or provider call.

This is a regression check, not an absolute accuracy threshold or certification of
reviewer independence. The actual private corpus, extraction outputs, retained pins
and deployment invocation are still to be established. The existing deployment
script has not been changed to run an unconfigured check. Unit fixtures only test
supplied declarations and do not establish a real independently reviewed corpus.
