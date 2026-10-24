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
