# r11-copy-audit: WIP notes

Unit: duplicate evidence principle (priority a). A printed period admitted twice
in the live ledger, missed by the admitted-duplicates detector and the wave
audit. Counts and opaque ids only (truth ids are file sha256 prefixes; case ids
are 8-character prefixes). Private detail: /mnt/owl-data/fin-real/tmp/r11/.

Base: fin/release-1 at cdb9e2b9. Branch fin/r11-copy-audit. Not pushed, not
merged, nothing written live.

## Landed commits

- 2a9a9b6b saved copies are found whatever reader read them, also across ledger accounts
  - `admitted_statement_duplicates`: copies grouped by currency and dates only.
    Besides the r2 rule, two saved copies are the same printed statement when
    their files are one document (identical bytes, or identical page images,
    `page_identity`) on the same pages, or they print the same account
    reference, currency and dates with at least one payment each. Money must not
    conflict (same payments and balance convention, printed balances of one a
    subset of the other's: the pre-admission `_money_conflicts`) and ledger
    payments and period balances must be equal. Product type and bank wording
    are not compared. Consolidated accounts compare as one.
  - a pair equal in everything but its ledger account goes to
    `split_across_accounts` with the account merge it needs (blockers mirror
    `account_consolidation.preview_consolidation`: bank, identifier, currency,
    product type) and `automatic` = files are one document. Set aside only with
    `across_accounts=True` and only for `automatic` pairs; rechecked under the
    row locks by `decide_duplicate(match='same_document_across_accounts')`.
    Accounts are never merged here.
  - switch `admitted_statement_duplicates.READER_INDEPENDENT` (False = r2 rule).
  - script `financial_set_aside_admitted_duplicates.py`: lists split pairs,
    `--apply --across-accounts`, `--render-pages` (dry run renders files of
    copies sharing a period, stores nothing).
  - `real_ledger_audit`: a live file belongs to a truth document also by its
    bytes (uploads after the inventory) and, with `--page-identities`, by its
    pages; new counts `same_printed_period_in_more_than_one_ledger_account` and
    examples.
- ecb917c2 a failed reading of the same pages follows the upload that was read
  (`review_queue._set_aside_read_copies`: stored page identity as well as bytes;
  `copy_reason` `same_pages_read`; frontend wording "Every page is the same as ...").
- d2398145 page identities for files already in Loupe: dry run and guarded backfill
  (`scripts/financial_page_identity_backfill.py`; `--apply` writes only the
  stored identity through the worker's `_record_page_identity`).
- 66ece78d backfill dry run counts against the stored decision (counter fix).
- c4580c20 the harness keeps draining readiness while work is pending
  (`drain_readiness`: stops only after 5 consecutive rounds that settle nothing;
  reports rounds, quiet rounds, drained or not; no scoring rule changed).
- b6758373 checkpoint B test waits for preparation to finish (the suite race).

## Rule measurement on truth (every pair of verified truth periods, 1,630 periods)

- same full printed account digits + currency + dates + equal money (payments
  amount/direction/date, opening, closing) with >= 1 payment: 168 pairs, all
  truth copies; **0 false copies**. With the last 4 digits only: same 168, 0 false.
- with 0 payments: 20 pairs, 3 copies and **17 false** (sub-accounts of one
  statement, same file), hence the payment rule.
- all 171 truth copy links share reference, dates and money.

## Item 1: live, READ ONLY (code 2a9a9b6b)

Set-aside dry run, all 6 cases (`financial_set_aside_admitted_duplicates.py`):

| Case | Saved copies | Set aside | Split across accounts | Held | Already set aside | Not compared |
|---|---|---|---|---|---|---|
| 1c75e65e | 53 | 0 | 0 | 0 | 0 | 0 |
| 267842f3 | 58 | 0 | 0 | 0 | 0 | 0 |
| 49494305 | 608 | 0 | 0 | 0 | 102 | 42 (no complete period) |
| d5b330d1 | 1,041 | 0 | **1** | 6 (other_bank_without_payments, pre-existing: same 6 with the switch off) | 1 | 66 |
| fdaf956c | 7 | 0 | 0 | 0 | 6 | 0 |

- The split pair: copy d7d1158e6b261#2 -> retained d9ff0d74d6f9a#2 (the
  retained copy carries investigator work), **57 payments counted twice**, proof
  `printed_reference` without stored identities; with `--render-pages` (730
  files rendered, read only) proof **`identical_pages`**, so after the page
  identity backfill `--apply --across-accounts` would set it aside. Account
  merge blocked by **product_types_differ** (one reader said savings, the other
  checking); the copy's account holds 3 other saved periods.
- No other pair found in any case (with and without rendering).
- Wave audit (`real_ledger_audit`, READ ONLY): same printed period admitted
  twice **0 -> 1** (d5b330d1 d7d1158e6b261#2), in more than one ledger account 1.
  Live periods audited 885 -> 1,129 (709 live files found by bytes that the
  inventory does not list; +3 by page identity with the r10 census cache:
  1,131). Outcomes: agrees 703 (705), convention_only 314, disagrees **6
  (unchanged)**, live_period_undated 106. Private: audit-r11-plain, audit-r11-pages.

## Item 3/6: page identity backfill dry run, live READ ONLY (code 66ece78d)

1,777 live PDFs rendered (0 unrenderable, 0 with a stored identity, 1,777 would
be recorded). 13 page-copy groups, 46 files, 114 live items, all in d5b330d1
(matches r10's census). For the 74 items the copy rule re-evaluates:
- set aside as linked copies 45 (13 newly), retained 23, still compared by a person 6;
- **possible-duplicate checks today (attention): 19 -> 6** once the identities are
  stored and the batches re-evaluated: 10 set aside as linked copies, 3 become
  the retained copy; 6 still need a person;
- set-aside copies that would return to the queue: 0.

## Measurements (frozen code b6758373 at bench-code/r11-copy-audit-b6758373)

- Synthetic (bench-runs/r11-copy-audit-b6758373): **108/125**, recoverable
  105/108, 0 wrong, 0 critical (366 rows), holds 10/10, copies held 1/1,
  duplicate contributions 0, no safety failure line. Readiness drain 4 -> 0 in 1 round.
- Real whole set: PENDING (see below).

## Tests actually run

- targeted: admitted duplicates 20 OK; duplicate/page-identity/real-truth/
  consolidation neighbourhood 230 (1 failure in page_identity_copies under load,
  passes alone 3/3; the unchanged base failed the same module 1 of 7 runs, test
  name not captured: pre-existing load flake); review queue 74 OK; benchmark
  harness 17 OK; page identity backfill 2 OK; checkpoint B gate 13 OK x2.
- full financial suite (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1, CLAUDE.md
  command) at 66ece78d: **Ran 6,520, failures=2 (the known unassigned_statement
  pair), errors 0, skipped 20** (wave 10: 6,503, failures 2, errors 1).
- frontend (as the app user): tsc -b 0; ReviewQueuePanel 15/15; vitest unit
  2,129/2,130, the failure LedgerTracingWorkbench (untouched) under load,
  7/7 alone. Live node_modules root-owned entries: 0 after.

## Not verified

- The across-accounts set-aside is only exercised on SQLite (synthetic). Its
  PostgreSQL path is decide_duplicate's existing one; `verified_readings` keys on
  the account identity, so a verified-class row in another account would refuse
  (fails closed).
- The backfill `--apply` was not run (live write). Settling the 13 checks also
  needs the items re-evaluated (their batch prepared again or the readiness sweep).
- Under forced one-file worker turns (TURN_SECONDS = 0) 5 other checkpoint B
  tests fail (single-turn assumptions for imports and deliberately interrupted
  turns); never seen failing in a real suite run; not changed.

## Proposal for dcfc8ce1f2afc#1, daf5c8337d9c7#1, ddbf23dd65ecf#1 (default OFF: not built)

The printed-facts rule above (equal printed reference, dates and money with a
payment, across two files) has 0 false copies on truth, but it cannot recognise
these three from their readings: in bench/wave10 dcfc's original d8af2d5c29493#1
reads with no account number, no bank and no opening balance (attention), and
for daf5/ddbf neither copy nor original has a reconciling reading (both
attention, nothing admitted). So no rule from printed facts in the readings
pairs them; they stay as they are. Note: for dcfc the statement counts once in
the ledger (the copy is saved, the unreadable original is not); REAL_EXIT=1
because the harness expects the original to be the saved one.

## Next unit

- Neil runs, after deploy: backfill (`financial_page_identity_backfill.py --case
  <d5b330d1 full id> --apply`), then the set-aside dry run (expect the split pair
  with proof identical_pages), then `--apply --across-accounts` for that case.
- The account merge for the split pair needs the product type corrected first
  (consolidation refuses different product types).

## Needs Neil

1. Live set-aside of the split pair (d5b330d1, d7d1158e6b261#2 / d9ff0d74d6f9a#2,
   57 payments counted twice): recommendation as above (backfill, then
   `--apply --across-accounts`, keep the copy with investigator work).
2. Which product type the account is (savings or checking): the source decides;
   then merge the two accounts through account consolidation.
3. dcfc scoring: whether "the readable copy is saved when the original cannot be
   read" counts as correct (a harness scoring rule; not changed here).
