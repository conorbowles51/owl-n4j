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
