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
