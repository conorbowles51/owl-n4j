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

## Unit C notes
# fin/aq-c-others: WIP notes (unit C, BNB2 waiting queue)

These notes hold counts and opaque document ids (sha prefixes) only. Real values and transcriptions are kept
under /mnt/owl-data/fin-real/aqc (mode 700).

## Scope

There are 72 targets: 56 are outside the truth corpus and 16 are in truth but held by the bench. The Santander
Consulta and Intercam/Kapital brokerage layouts belong to unit A, and the pipeline/re-read path to unit B.

## Measured on real bytes (mini corpus of 65 docs, base f2a52eae vs branch, readings reused)

The ready count went from 13 to 22 of 72. Wrong admissions were 0 in both runs, and critical-field errors were
0. No target and no admitted period was lost. The scored set has truth for 30 files: 17 tier-A, plus 13
t-visual transcriptions written for this unit and compiled VERIFIED.

| family (as resolved) | targets | ready before | ready after | what changed / why held |
|---|---|---|---|---|
| Monex (2022+ sideways, 2021 portrait) | 15 | 2 | 9 | profile names the 4 balance columns and the guarantee column |
| BBVA | 17 | 4 | 6 | OCR stroke between day and month (q51, q52). Held: 3 scans missing printed pages, 6 fund statements (not ledgers), q43 (OCR '141/JUL' day), q44 (currency) |
| Santander (B) | 21 | 5 | 5 | not reached in this unit |
| other (C) | 14 | 1 | 1 | Held: 9 BBVA scans missing printed pages (q61-q69), 2 brokerage currency (unit A), q38 balance, q58 |
| Kapital / Intercam | 4 | 1 | 1 | MXN sections not reconciled (amount columns) |
| Scotia | 1 | 0 | 0 | not reached |

The newly ready targets are q23, q24, q29, q30, q31, q35 and q39 (Monex), and q51 and q52 (BBVA). Every one is
scored against truth: the visual transcriptions cover docs dcefebd5, d89be099, deb1e564, d51c9120, d497c025,
d7849892, d4e0e81b, daf7e54f and d6b93449. The transcriptions of d5097dee, d4cc6be4, d4cb7388 and d532fd63 are
also VERIFIED and score their held sections.

Monex targets still held:

- q32 and q48 (EUR section, blank currency). The OCR reads the summary's opening label with a stray word, so
  the section splits after the currency heading.
- q33 and q27 (balance/reading).
- q45 and q46 (balance/reading).

## Engine: outline reading on sideways pages

Outline (vector glyph) reading previously ran only at rotation 0. Pages now OCR'd at 90, 180 or 270 read their
outlines in the turned frame (TurnedPage). The switch is TURNED_PAGES in vector_glyph_reading.py.

Across 21 truth docs with turned vector pages, the content changed in 17. Bench results on the 35 truth periods
from those docs:

- Product: base 28, branch 29, r14s-whole 28. Lost 0; gained df191ae7#1.
- Generic-only: the same, against r14s-whole-go. Lost 0.
- Wrong admissions: 0 in both modes.

On the aqc mini, new readings for the 8 sideways Monex docs changed nothing in the outcome.

## Regression

The Monex profile was checked by catalog equivalence on 87 truth docs, comparing base and branch in product and
generic-only modes. Ignoring routing seconds and layout fingerprint, the material catalog changes are:

- Product: df191ae7 (now proved), plus d23eb18d and dc0eacc0 (engine now agrees with library; served unchanged).
- Generic-only: those 3 docs.

The date-stroke rule's tokens occur in none of the 815 truth readings, so the truth catalog is unchanged by
construction.

## Tests

- New backend tests: DateSlashStrokeTests, and the Monex profile column roles.
- New engine tests: tests/test_turned_page.py, and the sideways glyph test in test_vector_glyph_reading.py.

## Gates (measured)

- Synthetic benchmark (branch): 0 wrong admissions; held 10/10.
- aqc mini, product and generic-only: 0 wrong admissions; 0 lost; generic-only ready 13 -> 22.
- Truth runs on 21 turned-page docs and 3 Monex docs: no period lost against r14s-whole or r14s-whole-go.
- Backend: 423 targeted tests pass. The wider financial suite shows the same 22 failures on base f2a52eae and on
  the branch (recovery/scheduler/re-read environment tests).
- Engine container: 117 passed and 50 skipped (the skips need a font). On the host, the font-dependent glyph
  tests (56) pass.

## Vision fallback reader (fin/rd-vision, 2026-10-24)
Counts and opaque ids only.

- backend/services/financial/vision_reader.py (switch LOUPE_FINANCIAL_VISION_FALLBACK, default on). Held statements
  only, never one with investigator work, a saved/set-aside/ready one, a document review or a fund statement.
  Trigger: a file prepared through the normal batch path (recovery re-read or any preparation) is marked
  (batch entry `vision_fallback`); a separate background task in the batch worker (`_vision_forever`, never
  inside a batch turn or a case lock) reads its held statements.
- One OpenAI request per statement: every page image (3 overlapping strips per page, labelled "Page N"),
  schema-enforced JSON (strict json_schema), every row citing its page. Workload `financial_vision` in
  ai_model_policy (OpenAI in every profile), default gpt-5.6-terra (LOUPE_FINANCIAL_VISION_MODEL overrides).
  llm_service.LLMExecutionContext.call_vision_json raises on refusal / truncation / non-OpenAI (fail closed).
- Accepted only when: opening + rows = closing to the cent; every printed running balance agrees; printed
  credit/debit totals and counts agree; rows inside the period; printed page numbering shows no page absent
  from the file; header agrees with the text reading wherever it read a value; the account (number + bank)
  has saved statements in the case, the printed currency picks its sub-account, the holder matches one of its
  saved statements; adjacent saved statements continue its balances and none overlaps it; every cleanly read
  text payment and text balance is in the image reading; the rows are not just the printed totals. Then the
  batch's own assess/admission must find nothing at all; only then a System review is saved (save_review),
  rows "Read from page image, page N.", text rows set aside with a reason (retained), and auto_save_prepared
  saves it as for any statement that checks out completely.
- Otherwise held as before, with the reason stored (file metadata `financial_vision_reading`, item summary
  `vision_reading`) and shown in the queue entry (`issue_messages`, "Page images: ...").
- Cost: per-statement record of tokens and cost (also per page), logged; cap per case per worker run
  LOUPE_FINANCIAL_VISION_CASE_BUDGET_USD (default 30). Read once per reading and model.
- Tests: tests/test_financial_vision_reader.py (28) + ai_model_policy, llm_service, queue_save, review_queue,
  review_queue_balances, import_batches: 279 pass.
- Truth tool: benchmarks/statement_automation/vision_truth.py (measure only, on a copy of a whole-set bench DB).
