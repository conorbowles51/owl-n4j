# r-subpoena: WIP notes (unit complete)

Counts and opaque ids only. Target: live evidence file 6e611846 in case 49494305 = truth id **dfc15d7fbdc2c**
(345 pages, a credit union's records production). Private detail: `/mnt/owl-data/fin-real/tmp/rsub/`
(dev tools, runs, replays), truth copy `/mnt/owl-data/fin-real/truth-r-subpoena/`.
Branch `fin/r-subpoena` from af76b2ac. Not pushed. Backend only (no evidence-engine change, no reading-revision bump).

## 1. Diagnosis (read-only)

- The file is one issuer (Navy Federal Credit Union): a cover letter, the subpoena and a certification (pages 1-8),
  **55 monthly statements of account** (pages 9-286; 52 of 5 pages, 3 of 6), then teller records and check images
  (pages 287-345). Text layer is digital (6 scanned pages, none in a statement). Each statement holds 4 account
  sections: checking, its line of credit (same 4 printed digits), savings, money market = **220 periods**.
- The production redacted everything before its window: the first statement's opening balances, summary and early
  rows are blacked out (dates left standing).
- Why it read as 286 attention periods with no identity (current code, live reading, page by page):
  1. each page's statement period was taken from the sentence 'for the dividend period from ... through ...'
     (a labelled range), so every page became its own period with wrong dates (B1);
  2. the production's own stamp 'Page k of 339' beside 'Page n of 5' counted as a second numbering (pages missing);
  3. the 'Items Paid' check list after each table read as movements;
  4. the credit line's card wording ('credit limit') set the card convention for every section on its pages
     (once the period was fixed, a savings section proved under the card convention, every direction inverted);
  5. identity: the account is printed only as '<product> - 1234' in each section heading; the holder only as
     'For <name>' under 'Statement of Account' on continuation pages (the address block prints no postal line);
     no page names a currency (bare '$'); quiet sections print 'No Transactions This Period';
     two-line entries (amount on the line below the date) were not read.
- No family reader claimed any page; no truth existed (inventory: needs_parser, visual-queue shard 18).

## 2. Truth (commit 511fe673)

Tier-A pdfplumber reader `parse_navy_federal` in `real_truth.py` (one period per section; running balance on every
row; the summary page's previous/ending balances and deposits/withdrawals totals per account as controls; two-line
entries; redacted rows never verify; a line of credit verifies only with no movements and outstanding total = principal).
5 synthetic tests (module 48 OK). Issuer detection changes for no other cached truth document (626 checked).
Generated into a PRIVATE COPY of the shared truth (`truth-r-subpoena`, `--only dfc15d7fbdc2c`): manifest = shared
manifest + this file, no other entry changed. Not written to the shared truth (other units' `--readings` runs would
fail on a new file without a reading); the integration session regenerates it (command below).
- Periods: **205 verified** (162 deposit: 54 checking, 54 savings, 54 money market; 43 quiet lines of credit),
  15 unverified (3 redacted deposit sections, 1 redacted + 11 lines of credit whose opening outstanding total is not
  printed). Document status partly_verified (the 15 cannot be settled from the images either).
- Visual check, value by value against rendered pages: 3 periods (a checking period with a two-line entry and its
  summary controls, a savings period, a quiet line of credit + money market) all equal.

## 3. Reader (commits 73622c7a, 651dc9dc, f9d6105c, c50ce8e7, 169e4d4a)

General engine rules (institution-free, fail-closed; knowledge file updated in 33fd312c):
- B1 accrual ranges ('dividend/interest period') are never statement periods; a period label cell with the range in
  the cell directly below is a labelled period.
- A3 a production's running page stamp (count spans the file, in step with the physical pages, printed beside another
  numbering on 2+ pages) is set aside; A2/A3 after a complete run, a page carrying only that stamp starts appended
  records (not part of the statement; never a page printing a period or a statement page number, never an unnumbered
  first page of the next run).
- E9 after a closing balance that ended the movements, a heading with other amount columns opens another table whose
  dated amount lines belong to no section; a total after such a closing totals another table.
- C5/A7 in multi-section statements card vocabulary counts only in the section's own lines up to its closing.
- E4 two-line entries are now an engine rule (2 layouts).
- B7 'No Transactions This Period' between equal balances proves a quiet section; the import cites it as source
  proof (`statement_printed_no_activity.printed_line_evidence`, bound at admission to both balance rows).
- A dated line printing nothing else, inside the table, in the movement-date form, holds the period (redactions).
- A6/A7 a credit line printing the same account digits as a deposit account of the same statement is held
  (`account_shared`): the ledger keys accounts by institution + digits and would merge them.
- Profile (data) `navy-federal`: `account_suffix_heading` (section account = '<product> 1234' from its own heading),
  `holder_heading` ('Statement of Account' / 'For <name>'), USD, institution. All-phrase profiles outrank
  single-phrase matches (a payment line names a card issuer).

### Result on this document (fresh engine reading of the file; live retained reading gives the same)

| | before (af76b2ac) | after |
|---|---|---|
| Periods found | 286 (wrong dates) | 217 (matches the 220 truth periods; the redacted first statement is one held period) |
| Ready without edits, verified truth (harness, mini corpus) | **0 / 205** | **161 / 205** (see pairing note) |
| Engine proved, equal to truth in dates, balances, every row, holder, currency, account | 0 | 161 / 162 verified deposit periods |
| Wrong admissions / critical-field errors | 0 / 0 | **0 / 0** (proof below) |
| Held | all | 42 quiet credit lines account_shared, 1 not_reconciled (one page whose cells merged), 1 quiet credit line, 15 unverified (redacted / principal-only credit lines) |

Harness (`run-after1`, code before the last two commits, which do not change this document's reading: same 161
proved, same holds) reported "156 ready, 23 wrongly admitted, 256 unexpected transactions": that is the harness's
greedy pairing crossing each checking item with the credit-line truth period of the same account digits and dates
(the 23 "wrong" periods are credit lines with no movements; the items paired to them hold the checking rows).
Re-paired by content (`dev/ledger.py`: each admitted item to the truth period of its closing date and account whose
rows it matches): **161 admitted periods, all 871 saved transactions equal to truth, no truth period used twice,
0 wrong**. c50ce8e7 now keeps the product name in the account reference ('EveryDay Checking 3701' vs 'Checking Line of
Credit 3701'), which the harness's pairing uses; the mini harness was not rerun on it (12 h on this host, below).

### Regression replay (stored wave-5 readings of all 583 truth documents, catalog + engine, base vs head 169e4d4a)
Engine-proved periods lost **0**; gained 1 (equal to truth); 845 proved in both with identical identity; 35 proved
periods now read under the deposit convention instead of amounts owed (identical money; truth = deposit for all 35);
routing: 1 library period newly cross-checked (agreement), 2 engine sections drop a heading and a dated line of
another table from their row scope (reading unchanged). Library code untouched. Three replay passes found and fixed
6 + 64 + 12 temporary losses (commits 651dc9dc, f9d6105c, 169e4d4a) before this result.

### Tests
- Engine module 132 OK (15 new; each fails on the code before its rule except stated guards).
- `test_financial_real_truth` 48 OK; `test_financial_import_batches` 93 OK.
- Full financial suite: see the last line of this file.
- Synthetic benchmark (f9d6105c): **105/125, recoverable 105/108, 0 wrong, 0 critical, holds 10/10** (= baseline),
  `/mnt/owl-data/fin-wt/bench-runs/r-subpoena-f9d6105c`.

## 4. Live effect: re-read only (nothing run)

Backend-only change: the file's saved reading is re-read; no engine job, no OCR.
```
cd backend   # service environment loaded
python3 scripts/financial_reread_file.py --case 49494305-dcd5-4821-8937-d99cfec3abd9 --file 6e611846-00e6-4cfc-904a-a868c5598911          # dry run
python3 scripts/financial_reread_file.py --case 49494305-dcd5-4821-8937-d99cfec3abd9 --file 6e611846-00e6-4cfc-904a-a868c5598911 --apply  # after deploy
```
Dry run on live today (read-only, 58 s): the file is in **4 batches** (408aef0b, f6f7cd42, c77b6f54, 16b0e9c2), all
'checked', 574 attention items, 0 with saved review; current reader: 217 periods, 161 proved, identity read on
217 (holder 216). `--apply` queues the file in all 4 batches (all or nothing; the queue lets the newest batch
stand per period). The worker re-prepares; untouched items of the old 286 periods are retired to
`superseded_reading` (commit 7795610f, switch `import_batches.RETIRE_VANISHED_PERIODS`; nothing is deleted;
fires only when a file is prepared again, never on deploy). The existing whole-batch path
(POST batches/{id}/refresh-statements) does the same for every file of a batch.

## Decisions for Neil
1. **Credit lines sharing the checking account's digits are held** (42 quiet periods here). Admitting them would put
   a card-convention period into the checking account's ledger identity. Reverse: drop `_hold_shared_account_credit_lines`
   once account identity can carry the product.
2. **Group import of 161 periods from this file took 9.6 h** in the harness (load 10-17 on 6 cores; preparation 12 min).
   Importing this file live will be slow; worth a look before Alex imports it (each period's import re-reads the
   345-page document).
3. Integration: regenerate shared truth with this branch:
   `PYTHONPATH=/mnt/owl-data/fin-wt/headless/real/pylib python -m benchmarks.statement_automation.real_truth --inventory /mnt/owl-data/fin-real/inventory.json --out /mnt/owl-data/fin-real/truth --cache /mnt/owl-data/fin-real/cache --only dfc15d7fbdc2c --jobs 1`
   and add the engine reading (`/mnt/owl-data/fin-real/tmp/rsub/engine-readings.json`) to the whole-set readings.

## Not done / next
- The harness's greedy pairing (same digits, same dates across sections) is a scoring artefact; not changed (benchmark rule).
- Visual settlement of the 15 unverified periods (redacted / principal-only) so the document becomes final.
- The one held checking period (cells merged on one page) needs the image path, not an engine rule.

Full financial suite on 169e4d4a: Ran 6,177, failures 5, errors 0, skipped 20. The 5 fail identically on base
af76b2ac (3 package-surface checks for modules of earlier units: batch_file_overview, batch_selection_preview,
review_queue; the known unassigned_statement pair). Frontend not touched.
