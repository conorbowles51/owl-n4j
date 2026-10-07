# r3-andrews — WIP notes (real wave 3)

Counts and opaque ids only. Private detail (diagnostic scripts, readings, per-statement comparisons, run
databases) is under `/mnt/owl-data/fin-real/` (listed at the end). Branch `fin/r3-andrews`, based on
fin/release-1 d36fd235. Not pushed, nothing merged, no live data touched, no services touched.

## Result in one paragraph

On the five scanned Andrews share statements (375 pages with an embedded OCR layer, 270 verified periods),
**199 periods are now ready without any edit, up from 99** (recoverable 199/266, was 99/266). There are
**0 wrong admissions** and **0 critical-field errors** in 2,091 saved rows. Every admitted period is equal to
the verified truth, row for row (a separate read-only check of the run database agrees: 199/199). Must-hold
periods kept out: 4/4. No period that was ready before is held now, in any family. No Andrews period is held
for its holder any more, so 0 holder confirmations remain (34 periods were held for that before).

## Landed

| Commit | What |
|---|---|
| 4ee786ff | Reader side: club shares (HOLIDAY / VACATION CLUB = savings sections); holder from the complete mailing block when the mailing code is absent or damaged; account number with spaces (only when an adjacent page prints the same nine digits); a stray mark in the title; spaces inside share-heading dates and IDs; `leading_continuation_rows`; pinned reading decided per account section, with neighbours confirmed in their role (amount/balance), joined cells needing an equation per unconfirmed part, and an unreadable amount no longer breaking the balance chain |
| bffe7375 | Engine side: crop readings compared by the amount they state; joined amount+balance cells crop-verified on Andrews pages (they were parsed unchecked), with per-part confirmation; decimal-mark-only page readings confirmed in canonical form; letter-for-digit, spaced and middle-dot page readings become targets (letters only ever through the pinned rule); the page reading offered to the pinned rule with one supporting crop; per-section repairs hand the remaining cells to the glyph reader; Andrews row dates read with letters are reread from their own cell; reading revision **v15**; 5eca9825 added to `AFFECTED_EXTRACTION_SHA256` |
| (this commit) | Notes |

**History rewritten (privacy).**
- The branch first carried 9 iterative commits: 0e64bfaf 9b79fe13 21dd7b9c 2d75a077 2d2c151f e05e7abd 42efa571, plus two notes commits (and one intermediate squash).
- Their messages, some code comments and some tests quoted real amounts and an account-number fragment from
  these statements.
- The branch was squashed into the two commits above. Every real value is replaced by a synthetic one.
- Nothing was ever pushed. The old commits are referenced by no branch, and this branch's and worktree's
  reflogs are expired. Their objects remain in the shared object store until a normal `git gc` prunes them;
  I did not run gc, because other sessions share the store.
- **The measured code is commit 42efa571. Its tree is identical to bffe7375 apart from comment lines and
  test values (checked with `git diff`).** Run ids below refer to it.

## Root causes BEFORE (wave 2 code 080664d2 and readings; 171 held Andrews periods)

Primary cause per held period, from `fin-real/tmp/r3a/rootcause.py` over the shared compare files and the
wave-2 readings:

| Root cause | Primary | Any |
|---|---|---|
| Crop rereads read the printed decimal point as a comma, so a correct cell never confirmed | 36 | 48 |
| Club share section (HOLIDAY/VACATION CLUB) never detected | 34 | 34 |
| Holder printed without (or with a damaged) mailing code line | 31 | 39 |
| Page marked incomplete by a club section, which also disabled the pinned repair | 15 | 15 |
| Continuation page not linked (account number read with spaces, title read with a stray mark) | 11 | 11 |
| Page reading not an amount (letters for digits, comma decimal), so it was never crop-checked | 8 | 23 |
| Share heading unread (spaces inside its date or ID) | 7 | 7 |
| Joined amount+balance cell (never crop-checked; amount read with a comma) | 6 | 43 |
| Closing / opening balance unreadable | 8 | 32 |
| Crops read the minus as "+" or dropped it at 300 dpi | 4 | 32 |
| Crop digits disagree / balance unreadable | 4 | 46 |
| Other (row date, direction, expected holds) | 7 | — |

## Root causes AFTER (final run r3a-run7, code 42efa571; 71 held = 67 recoverable + 4 must-hold)

| Root cause | Primary | Any |
|---|---|---|
| A held money cell the pinned rule cannot fix (adjacent disputed cells share their equations; first payment on a page whose previous balance is on the page before; crops and page disagree with no confirmed neighbour) | 33 | 39 |
| Row date unreadable (letters/punctuation the crops did not resolve) | 6 | 13 |
| Opening/ending balance on a page that is missing or not linked | 6 | 8 |
| Quiet section not proven (equal balances across a page break) | 6 | 6 |
| Repeated copy held for comparison | 6 | 6 |
| Payment verb misread (letters in the word misread): direction held by the existing sign/verb rule | 5 | 6 |
| Section not detected (share ID `ODDO`, account digit misread, date with a letter) | 1 | 6 |
| Orphan page needs a share assignment (existing grouped decision) | 1 | 5 |
| Other (running-balance mismatch, a line outside any payment, review check) | 3 | 7 |
| Must-hold / expected duplicate (correct) | 4 | — |

Harness blocking reasons, before → after: balance 103 → 41, reading 98 → 48, not_detected 41 → 1, holder 34 →
**0**, duplicate 8 → 8, no_activity 7 → 6, assignment 5 → 5.

## Numbers (counts only)

### Andrews mini-run: 5 documents, fresh engine read, final code (`fin-real/bench/r3a-run7`, REAL exit 0)

| Document | Ready before | Ready after | Recoverable ready after |
|---|---|---|---|
| d730f3e0d171f | 58/140 | **123/140** | 123/140 |
| d892131891936 | 2/36 | **19/36** | 19/36 |
| d1db0b3c9ca54 | 12/34 | **21/34** | 21/34 |
| da162973a4fa0 | 23/44 | **30/44** | 30/43 |
| d0f81a5b856d7 | 4/16 | **6/16** | 6/13 |
| **Total** | **99/270** | **199/270** | **199/266** |

- Previously ready periods lost: **0**. Gained: 100.
- Wrong admissions: 0. Critical-field errors: 0 (2,091 rows from 199 periods). Must-hold kept out: 4/4.
- "Duplicate ledger contributions" 63: these are exactly the 63 genuinely repeated payments (same account,
  amount, direction and date) in the verified truth of the 199 admitted periods. Each period was admitted
  once (199 distinct).
- Valid-looking wrong values proposed: 86 → **59** (date 53 → 30, amount 33 → 29). All are in held
  periods; there are 0 in ready periods.
- Investigator actions, Andrews (single / grouped): **2,493 / 2,430 → 1,579 / 1,560**. Field edits 1,078 → 277,
  rows to add 631 → 621, decisions 6 → 5, blocked periods not fixable by field edits 78 → 26. The run summary
  also counts the 30 unmatched orphan items: 1,609 / 1,590.
- Holder: 0 confirmations remain. The existing grouped `andrews-share/holder` decision has nothing left to do
  on these statements.
- Engine reading: pinned reading repaired 136 pages (207 cells), was 2 pages; joined cells crop-checked: 2,902
  confirmed, 113 held (they were never checked before); 8 row dates were reread.

### Whole truth set, backend change measured on the wave-2 readings (`fin-real/bench/r3a-full`, exit 0)

The run used 525 documents (the 4 added to the shared truth since wave 2 have no wave-2 reading). It used a
private filtered manifest at `fin-real/tmp/r3a/truth-full`. The reader code is identical to final; the
backend functions changed after it run only at engine time.

- **870 / 1,092 ready (wave 2: 821 / 1,089)**, recoverable 870/1,088.
- 0 wrong admissions, 0 critical-field errors (11,538 rows from 880 periods), must-hold 4/4, exact copies
  held 148/148.
- **0 previously ready periods lost (all families).** Gained 49:
  - 45 Andrews (reader changes alone on the old readings);
  - 3 Citi periods that are now verified in the shared truth;
  - 1 Capital One item that paired with the other one of an exact copy pair.
- Valid-looking wrong values proposed: unchanged at 89.

### Synthetic (`fin-wt/bench-runs/r3-andrews-final4`, code 42efa571, exit 0)

- **105/125** ready, 105/108 recoverable, 0 wrong, 0 critical-field errors (354 rows), holds 10/10,
  copies 1/1, 0 valid-looking wrong values.
- Andrews share: 43/46, with all 43 recoverable ready and its 3 must-hold/decision periods held.
- Per period against real-wave2: 0 lost, 0 gained.

## Tests actually run

- Engine, final code, live .venv with `OMP_THREAD_LIMIT=1`: 18 modules, **361 passed**:
  - new `test_andrews_scan_money_cells` (44);
  - existing: `test_andrews_pinned_reading` (32), money verification, second reader, generic repair,
    pdf_extraction, native reread, amount/date OCR, BBVA/Capital One cell OCR, Merrick repair, scan
    preprocessing, unread lines and others.
  - `test_pdf_worker` was not included. It fails 4/10 identically on the pre-change code: the spawned child
    cannot import the test module in this sandbox.
- Backend:
  - new `test_financial_andrews_scan_layouts` (18), all synthetic;
  - `test_financial_*andrews*` 76 OK; statement_import* 262 OK;
  - reading quality, page controls, generic pinned, unread lines, exports, recovery: 45 OK;
  - recovery readers / campaigns / estimate (pytest): 29 passed.
- Full financial suite on the final code 42efa571: **Ran 5,884, failures=2, skipped 20**. The 2 are the
  known `test_financial_unassigned_statement` pair, failing identically on the pre-change code (an earlier
  run at e05e7abd: 5,882, the same 2).
- Frontend: not touched, not run.

## Decisions taken (each reversible in one place)

1. **Crop readings are compared by amount** (`crop_money_value`).
   - A point read as a comma, or a speck after the cents, does not stop agreement. It applies to every family
     and is monotone: a cell confirmed before is still confirmed.
   - Reverse: use `money_value` for observations in `classify` / `_printed_readings`.
2. **A decimal-mark-only page reading (`-13,01`) is confirmed in canonical form** when four or more crops at
   both sizes state that amount. The page reading stays in the record (`normalised_text`).
   - Reverse: drop `_normalised_reading` from `verify_money_cells`. Those cells then go only through the
     pinned rule.
3. **The page reading is a pinned-rule candidate with one supporting crop at either size.**
   - c-andrews-residue had required two crops at both sizes.
   - Why: on these scans the 300 dpi crops read the printed minus as "+" or "2".
   - It is still accepted only when two confirmed printed balances fix exactly that amount and no other
     candidate.
   - Reverse: the support test in `_printed_readings`.
4. **Joined amount+balance cells are verified on Andrews pages.** Before, they were parsed unchecked.
   - Each part can be confirmed on its own.
   - A joined cell is pinned only when every unconfirmed part is fixed by an equation of confirmed values.
   - Reverse: the `pair` branch of `_target_kind`. That restores the unchecked parse, a safety gap.
5. **Andrews row dates on text-layer pages are reread from their own cell** (`_reread_row_date`).
   - It is the crop-consensus rule full-page OCR readings already had (six readings, the first and four
     or more at both sizes identical and inside the period), plus one more check: every page character
     must be that digit or a measured look-alike of it (O for 0, l for 1).
   - Reverse: drop the `('date', 'date_column')` candidate in `refine_statement_native_cells`.
6. **Letters for digits (`-B7.65`) are never confirmed directly.** They are only a candidate the agreed
   balances must pin.
7. **Club shares (`<WORDS> CLUB`) are savings sections.** Reverse: map them to `other` in `_share_type`.
8. **Unmarked holder.** The complete mailing block under the heading names the holder; the page-number
   position and a damaged code line may be passed over. Reverse: `_holder` returns `_marked_holder(rows)`.
9. **A spaced account number** (`1234 56 789`) opens a section only when an adjacent PDF page prints the same
   nine digits unspaced. On one real page the spaced digits were a misread, and that page is correctly not
   read.
10. Not done, because it would relax an existing hold: **a payment whose verb is misread** (letters in the word misread) could
    take its direction from its printed sign when the running balances agree exactly. The existing test
    `test_spaces_inside_printed_payment_verbs_retain_source_and_sign_checks` deliberately holds it.
    - Effect: 5 primary / 6 any held periods.
    - Needs Neil (below).

## Not verified / caveats

- **The import is slow on these scans.** The mini-run took 1 h engine read, then about 2 h of correction
  simulation, then 4.5 h of group import on a loaded host. The whole-truth --readings run took about 16 h.
  No harness code was changed.
- **The engine-time pinned functions.** The whole-truth run used the backend at 2d75a077. The later changes
  are in `statement_reading_quality` pinned functions only, which only the engine calls while reading, so
  that run does not exercise them. The Andrews mini-run does.
- **Other families' scans** keep every page reading they had. The tolerant crop comparison is the one
  general change; it only adds confirmations. No fresh read of non-Andrews documents was made, because only
  Andrews pages get the new targets.
- **Live.** Live sources gain nothing until deploy plus re-read (reader recovery: 5eca9825 is now listed).
- **The investigator's view.** The UI still does not show pinned or normalised cells beside the machine
  reading. This is the same gap as earlier pinned repairs; the records carry the page reading.

## What the next unit should continue (Andrews residue, 67 recoverable held)

1. **Cross-page equations.**
   - The first payment on a page has no previous balance on that page, and joined cells next to each other
     with both parts disputed block each other.
   - A backend pass at review time could apply the pinned rule over the whole period, using the stored
     crop observations (they are in the reading's refinement records).
   - About 33 periods.
2. **Row dates with letters that the crops did not resolve** (13 any). Same-cell crops at 450 dpi only, or the
   glyph reader on date cells.
3. **Verb misreads** (6): Neil's decision, below.
4. **Section not detected** (6): share ID `ODDO`; a heading date with a letter; an account digit misread
   (correctly refused).

## Decisions needed from Neil

- **Verb misread with agreeing balances.**
  - Should a payment whose Withdrawal/Deposit word is misread take its direction from its printed sign
    when the previous and new printed balances agree with it exactly?
  - Recommendation: yes. The sign and the two balances are three printed facts that agree.
  - Today such a row is held, by design. It would unlock about 5 Andrews periods.
- **Deploy with the rest of the release** (reading revision v15): engine and backend together.

## Private paths (not in git)

- Runs:
  - `/mnt/owl-data/fin-real/bench/r3a-run7` (final mini-run) and `r3a-run6` (pre-fix run, lost 2);
  - `r3a-full` (whole truth, --readings).
- Compare files: `/mnt/owl-data/fin-real/tmp/r3a/compare-run7`, `compare-full`. The shared compare dir was
  not written.
- Readings: `run7-readings.json`, `run6-readings.json`, `w2-andrews-readings.json` in `fin-real/tmp/r3a`.
- Tools: `fin-real/tmp/r3a/{rootcause,classify,estimate,replay,pin_debug,ledger_check,diag,page,srcs}.py`.
- Code snapshots per run: `fin-real/tmp/r3a/code-run*`.
