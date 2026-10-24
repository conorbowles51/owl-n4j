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

# Unit A2 — Neil decisions 2026-10-24: account currency + overlap trim

Branch fin/aq-a2-decisions, base 12e51fc7. Counts and opaque ids only.

## Code
- Rule 1, field_proposals (switch ACCOUNT_CURRENCY): a brokerage cash ledger (holdings_currency profile,
  reading flag brokerage_cash_ledger) printing no currency anywhere gets a currency proposal confirmed
  automatically from its ledger account's saved statements when they give exactly one currency (one saved
  statement suffices), identity exact+unique on two fields, no saved statement on the same dates. Basis
  'account_currency', label "account currency: same account's N saved statement(s)", saved through the
  System details save (audited with the basis). None / several currencies -> stays held (currency).
  A brokerage statement printing a currency (holdings) that differs from its account's -> held
  (statement_detail currency, can_import False) in the batch coverage stage.
- Rule 2, statement_overlap_trim.py (switch TRIM_OVERLAPS), called in read_statement_import for the
  movement-query form: trims only against SAVED statements of the same ledger identity (never waiting
  ones), exact copies/lineage excluded. Overlap rows must match one for one (date, amount, direction,
  running balance). Prefix/suffix trims only; middle cover / mismatch / missing balance -> held for
  overlap with the reason appended to the overlap note. Whole query covered with exact rows -> held
  (fully_covered, not saveable: saving would count twice). Kept rows: opening = running balance after
  last trimmed row (basis running_balance_before_kept_dates), closing on suffix trim = last kept running
  balance, totals = kept sums with printed totals recorded; whole query proved first; kept part re-proved.
  Trimmed rows stay in the reading, excluded, with covered_by (source doc) and reason "Counted once: ...".
  Trim is in the revision (writer re-reads under the case lock -> stale claims 409). Trimmed bounds saved
  as derived. Skipped for a query with a person's saved review; a query saved whole stays whole.
- Ordering: waiting queries rank by (start, end, file, statement); a query's overlap note ignores
  LATER-ranked waiting queries (they trim against it once saved) — batch coverage and import writer.
- Readiness: query items' fingerprint includes the case's saved-state mark; they are re-read when not
  current. queue_save.REVISIT_AFTER_SAVES: the sweep looks at a case's marked files again after any save.
- Harness: worker cycles after sweep saves (readiness -> sweep -> import, up to 12); ledger check scores a
  trimmed period against its kept dates and requires its trimmed rows to be held by another saved
  statement of the account; new metric movements_counted_twice (same account, date, amount, direction,
  running balance in two saved statements).

## Results (0 wrong admissions, 0 critical-field errors, 0 movements counted twice in every run)
- 11 no-currency brokerage docs: before 0 ready (held currency). Fresh read: 7 saved with account currency
  (their account has 1 holdings-currency statement saved, opaque 62d19a23), 4 held (their 2 accounts have
  no saved statement). Live mirror (live readings): 0 — the anchor statement's live reading is stale OCR;
  after its re-read (deploy note from unit A) the 7 follow. Live BNB2 saved brokerage state not checked
  (production reads not permitted to this unit).
- 7 overlap-held query items (live mirror): before 7 held overlap -> after 7 saved trimmed; all 13 distinct
  query periods auto-saved, copies set aside 7/9 as before. Fresh read: before 6 held -> 5 saved trimmed,
  1 held fully_covered (every movement already in a saved, longer query).
- Extended private mini (targets + 21 related docs of the same accounts), unit A code vs branch:
  auto-saved 22 -> 35, lost 0, gained 13 (8 brokerage, 5 query). Both runs flag the same pre-existing
  copy (a reprint whose original is outside the mini corpus) — identical in base.
- Synthetic (wave13 readings): 108/125 ready, 108 auto-saved, 0 wrong — identical to base.
- Tests: 15 targeted files (unit A set + import_batches, queue_save, harness) + 15 further affected files
  + new test_financial_statement_overlap_trim.py (14) + 9 account-currency tests: all green.

## Not done
- Whole-set harness vs r14s-whole not run (shared host); catalog/currency digest unaffected by these
  rules (trim is post-catalog, account currency is a proposal), unit A's equivalence diff still open.
- Removing an import that covers a trimmed query does not re-open the trimmed query automatically:
  find them by covered_by on the trimmed statement's saved request rows.
