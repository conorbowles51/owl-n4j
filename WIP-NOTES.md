# r2-admitted-duplicates — WIP notes (codes and counts only)

Branch `fin/r2-admitted-duplicates`, based on fin/release-1 8338cebe. Not pushed, not merged, nothing written live.

## Landed

- **f97dbdfd** r2-admitted-duplicates: statements already saved twice count once, both kept.
  - `backend/services/financial/admitted_statement_duplicates.py` (new, product code): detector
    `find_admitted_duplicates` (read only), `set_aside_copy`, `restore_copy`, `keep_copy` (swap, one transaction),
    `set_aside_admitted_duplicates` (whole case, one commit per copy), `sync_batch_items`, display helpers.
  - `duplicate_decisions.decide_duplicate`: new `match="same_printed_statement"` (equal money re-checked under its
    row locks), `basis` recorded on the adjudication (before None / after basis), `commit=False` for combined decisions.
    Default behaviour unchanged.
  - `statement_import.read_statement_import`: an excluded saved copy carries `current_import.duplicate_disposition`
    (label "Duplicate - Ignored by system" for the system set-aside, "Duplicate - Excluded by investigator" otherwise,
    reason naming the retained file and page); a retained copy carries `current_import.duplicate_copies`.
  - `import_batches.assess`: an excluded saved copy is `duplicate_ignored` (0 payments), not `imported`.
  - `pending_statement_duplicates.apply_duplicate_disposition`: returns the document decision for an excluded saved
    copy instead of persisting "retained" for it.
  - Router: `POST /api/financial/documents/{id}/keep-duplicate-copy` (case edit access, actor + reason); the existing
    duplicate-decision route now brings batch items along (best effort, after commit).
  - `backend/scripts/financial_set_aside_admitted_duplicates.py`: dry run by default (READ ONLY transaction + ORM
    write refusal, reused from financial_reader_recovery_estimate), `--apply` (needs `--case` or `--all-cases`),
    `--restore <document>`, `--keep <document> --reason`, `--out DIR`.
  - Frontend: `KeepDuplicateCopy` form in the statement review of a system set-aside copy; reason + retained
    file/page shown; retained copy lists its set-aside copies.

## Rule (as built)

Same printed period (`same_statement` or `same_printed_period`) AND equal money: reading payments + printed balances
equal (`statement_content`), ledger payments + period balances equal, same ledger account. Otherwise held with a code
(money_differs, ledger_differs, account_differs, edits_differ, reading_not_comparable, other_bank_without_payments,
rows_corrected, retained_rows_set_aside, unverifiable). An investigator reason for keeping both
(`coverage_review_reason`) -> `kept`; a restored copy -> `restored`; both left alone by every later run.
A reading whose unresolved rows were all excluded in its saved review is a complete reading of what was saved
(needed for 4 live pairs: the first production's reading had 1 unresolved row each, excluded by the investigator;
reading money, ledger money and account equal).

## Retained copy: the prompt's rule did NOT hold; decided and built a different general rule

- Prompt rule "copy admitted first (earliest import)": on live case 49494305 it keeps the FIRST production
  (d568d90faff56 / d22e405327ccf) for only 54 of 102 periods (30/50 and 24/52) and splits each production across both
  files, because concurrent batch workers saved one upload's periods in no evidence order (all 4 files share one
  upload instant). Per file, earliest first save picks d568d90faff56 but df7e9c5f8cbb0 (not Neil's choice).
- Built (one rule, no per-case choice): investigator work first -> evidence received first (original upload of a
  reread) -> file-name order, digits as numbers (Bates order for files received together) -> first page in file
  (reprint keeps first printing) -> first saved -> id. Live: picks d568d90faff56 and d22e405327ccf for **102/102**.
  Reverse in one place: rank by `document.created_at` first in `_rank`.
- Per the prompt ("if it does not, report and stop short of enabling"): `--apply` has NOT been run and should not be
  run until Neil accepts this rule (see needs-Neil).

## Live dry run (read only, committed code f97dbdfd, 2026-10-06; private detail /mnt/owl-data/fin-real/r2dup/)

| Case | Saved copies | Set aside | Payments leaving totals | Held | Already set aside (earlier decisions) | Not compared (no complete printed period) |
|---|---|---|---|---|---|---|
| 49494305 | 275 | **102** | **929** | 0 | 0 | 42 |
| d5b330d1 | 289 | 0 | 0 | 0 | 1 | 66 |
| f887b0d9 | 255 | 0 | 0 | 0 | 0 | 9 |
| fdaf956c | 7 | 0 | 0 | 0 | 6 | 0 |
| 1c75e65e | 53 | 0 | 0 | 0 | 0 | 0 |
| 267842f3 | 58 | 0 | 0 | 0 | 0 | 0 |

Per file pair (49494305): d624d41045389 -> retained d568d90faff56: 50 periods, 629 payments;
df7e9c5f8cbb0 -> retained d22e405327ccf: 52 periods, 300 payments. Pairs held because money differs: 0.
Matches the earlier audit (102 periods / 929 extra copies). First dry run (before the excluded-unresolved-row rule)
held 4 of the d624d41045389 pairs as reading_not_comparable (98 / 907).

The 5 live periods that disagree with truth: df7e9c5f8cbb0#2 and df7e9c5f8cbb0#12 disappear with the set-aside;
their retained twins d22e405327ccf#2 and #12 carry the same misreading and stay until re-read; de45aa4468c66#1
(Monex) is untouched.

## Tests actually run

- New `tests/test_financial_admitted_duplicates.py`: 10 tests OK (separately produced copy with Bates-order
  retention, restore + not undone by next run, swap, third production + swap, different money held and refused by
  the product decision, edited copy kept, recorded reason respected, other case untouched, reprint inside one file,
  comparable-reading unit).
- Neighbouring suites (16 modules incl. duplicate decisions/query/router, pending duplicates, overlap, reprints,
  statement import, card, import batches, graph followup): 410 OK.
- Full backend financial suite (CHROMADB_PORT=1): Ran 5,819, failures 4 = 2 known `unassigned_statement` + 2 mine
  (route registry, package exports), both fixed and rerun: 49 OK in those modules.
- Frontend: tsc -b 0; eslint on changed files 0; vitest unit **296 files, 2,058 passed** (was 295 / 2,054).
- Synthetic benchmark (bench-runs/r2-admitted-duplicates-final): **105/125 ready (84.0%)**, recoverable 105/108,
  **0 wrong admissions**, 0 critical-field errors, held kept out 10/10, exact copies 1/1. Unchanged from wave 1.

## Unverified

- Real-document benchmark not re-run (~12 h). By construction it is unaffected: a fresh import never produces a
  superseded saved copy (pre-admission copies are set aside by r1-reproduced), so every changed path is a no-op there.
- PostgreSQL semantics of the set-aside (row locks, the one-active-statement constraint on restore/swap) only exercised
  on SQLite; decide_duplicate's PG behaviour is the existing path. A restore that would make a second active copy of the
  same evidence file + statement id is already refused by decide_duplicate.
- 42 saved copies in 49494305 with no complete printed period (start not printed / undated) are never compared.
- Graph redraw after `--apply` relies on the service's drift check for already-projected cases (not run here).

## Next

- After Neil accepts the retention rule and after deploy: from `backend/`,
  `python3 scripts/financial_set_aside_admitted_duplicates.py --case <case 49494305 full id, /mnt/owl-data/fin-real/census/case-ids.txt>` (dry run,
  expect 102 / 929 / 0 held), then the same with `--apply`, then the dry run again (expect 102 already set aside).
- Integration: no migration; engine untouched; frontend + backend deploy together (new route used by the review).

## Needs Neil

1. **Retention rule**: accept "investigator work, then evidence received first, then file-name (Bates) order, then
   first page, then first saved" instead of "earliest import" (which keeps the first production for only 54/102 live
   periods). Default if no answer: the built rule; `--apply` is not run by this unit either way.
2. **Run `--apply` for case 49494305** from the interactive session after deploy (102 periods, 929 payments leave
   totals; both productions stay in the case, linked, reversible).
