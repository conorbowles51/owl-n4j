# Integration of BNB2 queue units (A2 decisions, B Santander gap, C others)

## Unit A2 notes
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

## Unit B notes
# aq-b-santander: BNB2 waiting statements the bench saves but live holds

Counts and opaque ids only. Scratch evidence (private, mode 700): /mnt/owl-data/fin-real/tmp/aqb.

## Target set
- 64 live held statements in the truth corpus (units B 42, C 22); 50 of them are file-level saved by
  bench r14s-whole ("the 50"); 36 period-level (same dates).
- Live: all 64 held before. 62/64 live readings come from older engine revisions; the deployed engine
  digest is the same in base and in release-1 (390680fa).

## Cause, measured in a disposable batch (no investigator input)
| readings | code | targets ready (of 64) | of the 50 |
|---|---|---|---|
| retained live readings | base f2a52eae | 10 | 10 |
| bench readings (w13) | base | 34 | 32 |
| bench readings (w13) | + wave 14 (390680fa merge) | 37 | 35 |
| fresh current-engine reads (54 originals) | base | 34 | 32 |
| fresh current-engine reads | branch head | 37 | 35 |
- (b) stale engine readings: +24; (a) wave-14 code not deployed: +3.
- (d) person work: 34 targets carry saved progress or review requests by an investigator (must stay held).
- (c) batch/file-level guards: base campaign reasons for the 64: removed 26, investigator_edits 15,
  saved_import 10, duplicate_decision 10, reader_not_affected 2, eligible 1.

## Changes (branch)
- 319293fc merge of release-1 390680fa (wave 14).
- 216c5a6b re-read selection: restart after a removed batch, settled siblings (System-saved or System
  set-aside items no longer protect), failed idle batch members, selection rule in the release id
  (new id statement-recovery-engine-dfc2db02...).
- 7e238245 stale ready listing of a statement already saved is settled.
- 1c514593 / 0ba6ca50 copy_of_saved: held statement whose account (last six digits) and period the case
  already admitted is left for the duplicate workflow (fail closed; caught 2 truth duplicates the
  re-read would have saved and 9 periods admitted under another statement key).

## After (live read-only selection x fresh+branch measurement)
- 64: saved_new 5 (all equal to truth: balances, currency, rows); selected but still held after re-read 7
  (balance/reading 4, currency 2, account+balance 1); not selected: investigator_edits 30,
  copy_of_saved 12, duplicate_decision (person) 6, investigator_decision 2, reader_not_affected 2.
- the 50: saved_new 5; copy_of_saved 10; investigator_edits 27; duplicate_decision 5;
  investigator_decision 2; held after re-read 1.
- Wrong admissions on targets: 0 (2 truth-duplicates protected by copy_of_saved).
- Case-wide selection under branch rules: eligible 51 (base 14), copy_of_saved 47.

## Tests
- 18 targeted backend files: head 529 passed / 20 failed; base 512 passed / 20 failed; the same 20
  fail on base (pre-existing). Engine not touched.
- Synthetic bench (frozen code 216c5a6b; later commits touch only recovery selection): ready 108/125,
  wrongly admitted 0, duplicate ledger contributions 0, held kept out 10/10.
- Whole-set product bench on frozen code: started (bench/aqb-216c5a6b), about 10 h; generic-only not run
  (host shared, 6 CPUs, one bench at a time).

## Carry investigator work onto the re-read (decision 2026-10-24)
- 3771ef7e: statements with saved progress or batch drafts are re-read; her detail/row edits are carried
  onto the new reading (hers win), hand-added rows kept in place, the carried review stays hers (never
  System-saved), her original stays on the earlier reading (carried_from + per-file carry log). A review
  saved after scheduling is refused (work fingerprint). Not carried, stays held with reason: rows not
  aligned, statement/row ambiguous, work in another batch, two different drafts. Person decisions untouched.
  Switch LOUPE_FINANCIAL_RECOVERY_CARRY_EDITS.
- Worked statements in the 25 files of the formerly investigator_edits targets (35): carried 6 (4 exact
  baseline, all System-filled details; 2 unproven baseline, a person's row edits); not carried 29
  (rows_not_aligned 15, work_in_another_batch 5, statement_ambiguous 3, row_ambiguous 1, two_drafts 1,
  plus 4 on the original's source reading).
- The 2 statements carrying a person's carried edits stay held after carrying (row reading checks).
- Final, the 64: ready 8 (all saved, all equal to truth, none already admitted live); held: copy_of_saved 14,
  after re-read 11, sibling work not carried 10, own work not carried 8, duplicate_decision 6,
  investigator_decision 4, reader_not_affected 2, not_all_held 1.
- The 50: ready 8 (saved 8); held: copy_of_saved 12, sibling work not carried 10, own work not carried 8,
  duplicate_decision 5, investigator_decision 4, after re-read 2, not_all_held 1.
- Disposable carry run: 36 saved periods, 36 equal to truth, 0 differ.
- Case-wide live selection under head rules: eligible 111, copy_of_saved 97, saved_import 137.
- Tests head: 18 targeted files + review_carry: 536 passed / 20 failed (same 20 fail on base);
  6 files touching review recovery: 210 passed.

## Release untouched periods of a split file carrying her work (decision 2026-10-24)
- Rule (review_recovery.recovery_state, switch LOUPE_FINANCIAL_RECOVERY_SPLIT_RELEASE): when every
  uncarried earlier record that the new reading cannot place is file-level work, and the new reading names
  several periods, a period proceeds through normal readiness/auto-save only if none of that work touches
  it: no saved row of hers dated in its range (her date, else the earlier reading's date for that row id),
  no overlap with her request's period or any period imported from her reading (no double count), no
  shared row id and no shared page. Any row that cannot be dated, or any named-period work, keeps the whole
  file held as before. Her records are not changed. Released periods record split_from_held_work (held
  review ids, earlier readings, period) on the batch item summary and on the imported source document.
- Measured on the 10 (9 files), read only: all 22 uncarried records are file-level full snapshots of an
  old parse (mostly undated header rows; 21 file-level, 1 named); 0 can be dated, and on every file her
  rows sit on every page of every period of today's reading. Released 0 of 10: all stay held correctly.
- Counts unchanged: the 64 ready 8; the 50 ready 8 (sibling work not carried 10, now held by rule, not
  by default). Wrong admissions 0, lost 0, no live writes.
- Tests: 20 targeted files: 590 passed / 20 failed (the same 20 pre-existing failures); 5 new rule tests.
- Whole-set bench (bench/aqb-216c5a6b) still running at 02:20 UTC (918 of about 1944 batch items).
  Compare when done: python3 /mnt/owl-data/fin-real/tmp/aqb/compare_whole.py /mnt/owl-data/fin-real/bench/aqb-216c5a6b
  (per-period lost/gained vs r14s-whole results-rescored.json; script self-check on r14s-whole: lost 0).

## Do her uncarried records hold real edits? (read only, 2026-10-24 02:35 UTC)
- Script fin-real/tmp/aqb/baseline_classify.py (+ baseline_diff.py, baseline_proxy.py); private output baseline-classes.json.
- Baseline recovery: today's code reproduces the saved-on reading for 1 record only (revision match). Others recovered
  through the account-detail audit (an entry at the same instant: before/after/actor; rows verified unchanged vs her
  previous save on the same revision) or provable work (hand-added rows, row changes between her own saves).
- 48 uncarried records (the 22 sibling + 26 on the worked statements incl. source-reading and row-less drafts):
  a 1, b 4 (audited System fills: holder 2, currency 2), c 31, d 12.
  c: statement details only 25 (holder 16, account 13, institution 12, currency 3 field-touches; audited, by the investigator);
  rows 6 (hand-added rows 15 / 4 x4 records with 1 row changed and 1 row note / 19). d: unaudited first saves on
  readings today's code does not reproduce (no hand-added rows, no notes).
- The 22 sibling: a 1, c 14 (all details-only), d 7. No record carries a statement note; 1 carries a row note.
- Eligible if a/b = "no edits to keep": 3 of the 18 held by uncarried work (3 of 64, 3 of 50: own_work f0e365/77fb6f/
  64a961 statements, System-only fills); 0 of the 10 sibling-held.

## Settle System-only work, carry details-only work with a payment match (decision 2026-10-24)
- e43ecebe, reread_carry.plan_statement (switch LOUPE_FINANCIAL_RECOVERY_DETAILS_CARRY, default on):
  - no edits to keep: every saved record of the statement is System's (a batch draft with no saver counts as
    System only when its request equals a System save) and no person is in its save or detail history ->
    settled, not held; the new reading is prepared like any other.
  - details carried, payments matched: row-by-row carry failed on row alignment, and her work is details only
    (no hand-added row, row note, statement note or confirmation; rows unchanged between her saves). Her
    holder/account/institution/currency (and period dates on a named statement) are set exactly; rows are the
    new reading's; every payment of hers (date, amount, direction; amount-free undated lines ignored; an
    undated payment holds) must have its own counterpart, excluded ones as excluded. Extra payments counted
    on the item (summary.reread_carry.details.extra_rows) and pass normal readiness. Saved as System
    (queue_save.system_filled_only accepts the basis); her saver is kept on the carried record.
  - file-level work: per period of the new reading; released when her payments dated in it match, the
    printed account (last six) and currency agree with hers, and no period imported from her reading
    overlaps. Released periods listed per record in financial_review_details_release (recovery_state stops
    holding them); the rest stay held with per-period reasons in the carry log.
  - Her original records are never changed; carried_from names them (basis recorded).
- Measured (fresh readings, disposable SQLite, live inputs read only; scripts live26.py, measure_details.py,
  detailsjoin.py; private outputs details-export.json, measure-details-fresh.json, details-join.json):
  - plans for the 31 worked statement keys: settled 9, row-by-row carried 2, details 1, per-period 7 (all
    periods proven on 7 files); held: no_period_proven 3 (multi-currency files: the other account's period
    differs in currency; overlaps with an imported period), statement_ambiguous 3, work_in_another_batch 3,
    hand_added_rows 2, two_drafts 1. Per-period holds: currency_differs 4, overlaps_imported_period 3.
  - the 64: ready 8 -> 12 (all saved, all equal to truth); held: copy_of_saved 14, after re-read 17,
    own work not carried 5, sibling work not carried 3, duplicate_decision 6, investigator_decision 4,
    reader_not_affected 2, not_all_held 1. Lost 0.
  - the 50: ready 8 -> 12 (saved 12); held: copy_of_saved 12, after re-read 8, own work not carried 5,
    sibling work not carried 3, duplicate_decision 5, investigator_decision 4, not_all_held 1. Lost 0.
  - gains: 3 System-only statements (the 3 expected), 1 file-level details carry. 6 sibling-held targets are
    no longer held by her work; they stay held by normal readiness after the re-read (other named periods).
  - every saved period of the disposable run: 24 saved, 24 equal to truth, 0 differ, no truth period saved
    twice. No live writes (live session read-only at the database).
- Tests: targeted 19 files: 553 passed / 20 failed, the same 20 as base; recovery readers file 61 passed
  (11 new: details carry, payment mismatch, hand-added rows, row/statement notes, undated payment, rows changed
  between saves, System-only settle and its history guard, per-period release, end-to-end carry + System save,
  switch off).
