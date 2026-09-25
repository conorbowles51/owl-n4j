# Correct printed totals before statement import

## Report and investigator objective

Alex reported that a statement's calculated closing balance matches its printed
closing balance, but import remains disabled. The screenshot identifies separate
money-in and money-out checks against two recorded printed totals of zero. A
matching closing balance does not resolve those separate checks: equal missing
credits and debits could leave the closing balance unchanged.

The original statement filename/source is still required to establish why these
two controls are zero. Backend inspection and synthetic reproduction establish
that an absent total is not defaulted to zero. A zero comparison comes from an
identified source control or a saved correction. Do not infer that the actual
statement is reconciled, overwrite totals with calculated amounts, clear known
controls, or waive admission based only on this screenshot.

The workflow must let the investigator inspect and correct the exact printed
total beside its source, save that correction, reopen it, and import once when
all checks pass. The original reading and current correction remain distinct.

## Connected correction repair

- Both the reconciliation blocker and detailed printed-total check open the same
  inline editor, rather than routing one through a generic balance field.
- Credit, debit, fee and interest totals have explicit labels, validation and
  focus targets. The editor retains source page/row and original reading.
- Hidden excluded rows remain hidden; selecting a control reveals its editor
  without changing the investigator's filter. Correction-page indices are
  clamped, and malformed-total review links return to the same active input.
- Corrections use the existing source-bound balance field and review persistence.
  Source kind, total direction/scope, transaction amounts and admission policy are
  unchanged. A missing or unreadable identified total remains a review blocker.

## Acceptance and release

The focused unit and browser journeys use synthetic statements. Backend checks
exercise matching closing balances with two erroneous zero totals, one corrected
total, cleared controls, both corrected totals, saved reopening, retained source
values/reasons, and import exactly once. Chromium covers both source-entry paths,
amount focus, excluded-filter stability, malformed-input recovery, save/reopen,
and desktop/mobile layouts. An additional actual FastAPI/Chromium journey checks
the correction-to-import workflow against disposable database persistence.

Local validation passed: 112 connected backend tests, 62 focused UI unit tests,
two Chromium journeys at 1280px and 390px, and one additional actual
FastAPI/Chromium correction/save/reopen/import-once journey. Independent review
found no admission, draft-retention or read-only regression. Type checking,
targeted lint and the production build passed. Synthetic screenshot inspection
confirmed the labelled editor and source context. Test assertions were corrected
to use the application's actual save receipt and restore file selection when
reopening after import; no production behavior was altered for these assertions.

Release revision and live acceptance remain separate from these local results.
The screenshot's source-specific diagnosis remains open until its original is
identified. No client statement has been changed to demonstrate the repair.

Post-release check: commit `18567e11` was pushed and automatic deployment succeeded
in 256 seconds, starting at 18:51:56 UTC on 25 September. The captured successful
deployment log and fresh Updates page identify that exact revision. Ingestion
gates were idle. The user was warned before publication about the brief service
transition. The deployed test batch and saved statement review reopened normally;
its available readings were already imported, so the new pending-total editor was
not demonstrated there by replacing saved records solely for a test. The complete
correction/import journey remains verified against the real local API and database,
not Alex's unidentified statement. These final verification notes were retained
locally and included with the subsequent balance-correction implementation,
avoiding another deployment solely for documentation.
