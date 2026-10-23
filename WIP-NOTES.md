# Unit A (Alex queue) — approved Santander query + brokerage currency

Branch fin/aq-a-approved, base f2a52eae. Counts and opaque ids only.

## Code
- statement_import_santander_query.py (switch MOVEMENT_QUERY): online movement query detected by its
  printed title, issuer legal line, 10 header labels repeated identically per page, page "i de N", one
  movement heading table per page. Opening = first printed running balance minus first movement
  (balance_basis printed_opening_after_first_movement); admitted only when printed Saldo Inicial equals
  the first running balance, movements oldest first, counts/totals/closing/running balances all agree,
  every page present, every line on the printed account. Otherwise held (no opening, unresolved row).
  Institution taken from the legal line so the query joins the monthly statements' ledger account.
- statement_engine.py (switch HOLDINGS_CURRENCY) + _BROKERAGE_CASH.holdings_currency: a brokerage cash
  ledger takes the one currency code its holdings table prints; none or several = held.
- statement_currency: 'printed_holdings_currency' accepted for the generic layout.

## Targets (35 items; 20 query, 15 brokerage)
Live mirror (live readings, live items incl. 9 duplicate uploads):
- before: 0 saved / 35.
- after: query 6 saved, 7 copies set aside as duplicates, 7 held overlap (online queries overlap one
  another); brokerage 0 saved.
Fresh read (bench readings, 26 distinct docs): before 0; after 14 proven, 8 auto-saved
(7 query + 1 brokerage), 6 query held overlap. 0 wrong, 0 critical-field errors (194 txns).

## Held, honest reasons
- brokerage 11 docs: no currency printed anywhere on the statement (checked against renders) -> needs a
  decision (case-level/account-level currency rule).
- brokerage 1 doc (opaque 42dc6ddb): opening not printed, identity unread -> held.
- brokerage 5 live items: live reading is an older OCR reading; current engine reading saves 1 of them
  (opaque 62d19a23) after re-read.
- query 7: overlap between online queries of the same account (by design held; needs trim rule decision).

## Truth
13 query docs: visual transcriptions record the derived opening; status unverified -> verified (auto).
Applied to shared truth via real_truth --only (backup truth-backup-pre-aqa); shared status now
verified 806 / not_statement 17 / unverified 5 / settled 4.

## Gates
- synthetic (wave13 readings): base 108/125 ready, branch 108/125, 0 wrong both.
- mini real (product and generic-only): 0 wrong.
- targeted backend tests: 489 + new green.

## Deploy
- No migration. Re-read the 4 stale brokerage live readings with the current engine.
- Readiness refresh sweep picks up held items after deploy.

## Real-set equivalence (in progress at hand-off)
Catalog+currency digest of every real reading (815, readings-w13-plus18), base vs branch code, product
source path. Whole-set harness vs r14s-whole NOT run (10h). Integration must finish this diff:
results private under fin-real/tmp/aqa/equiv-*.jsonl; any differing doc outside the 26 target docs is a
blocker.
