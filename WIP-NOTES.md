# r5-andrews-cards — WIP notes (real wave 5)

Counts and opaque ids only. Private detail (tools, readings, per-statement comparisons, run databases) is under
`/mnt/owl-data/fin-real/` (listed at the end). Branch `fin/r5-andrews-cards`, based on fin/release-1 b484f376
(a15230a0 + workfile). Not pushed, nothing merged, no live data written, no services touched.

## Result in one paragraph

On the whole real truth set (567 statements, 1,237 distinct verified periods; wave-4 readings for 560 documents plus a
fresh engine read, reading revision v17, of the 5 Andrews statements, Merrick and Credit One), **1,072 periods are ready
without any edit, up from 1,034 (83.6% -> 86.7%)**, with **0 wrong admissions**, 0 critical-field errors (15,371 saved
rows from 1,082 admitted periods), must-hold 4/4, exact copies held 148/151 (unchanged), 22 batch items matched to no
truth period (was 37), **0 of them offered**, and **0 previously ready periods lost** (38 gained: Andrews 31, Merrick 7).
Andrews 200 -> **231/270** (recoverable 231/266), Merrick 16 -> **23/42**. Both of Neil's rulings of 2026-10-09 are
implemented, each switchable in one place. Synthetic 105/125, 0 wrong, exit 0. Investigator actions on the 567
statements: 994 -> **815** per 100 statements one at a time, 961 -> **786** grouped.

## Landed (commits on fin/r5-andrews-cards)

| Commit | What |
|---|---|
| 6107800b | **Neil ruling 1** — Andrews payment whose Withdrawal/Deposit word is misread takes its direction from its printed sign only when the previous and new printed balances agree exactly (`MISREAD_VERB_DIRECTION`, `direction_basis=printed_sign_and_balances`) |
| 0ffae4ed | **Neil ruling 2** — card purchase and posting dates both just before the cycle: the posting date anchors the purchase (`card_row_dates`, `LATE_POSTED_CHARGES` switch for the whole late-posted rule; saved-statement proposal accepts the new basis) |
| e6997a9b | Andrews continuation notice read with spaces/points (`_continued`); pinned reading propagates pinned cells (`PROPAGATE_PINNED`); **whole-period pinned reading across pages** (new `andrews_period_pinning`, `PERIOD_PINNING`); engine stores `printed_readings` for held cells; crops reading a minus as 2/+ support the page reading (candidate only); reading revision **v17**; r4-cards' pdf_extraction digest b9248b80 added to the reader-recovery list |
| 39a45f8f | Andrews continuation-only pages (cycle with a look-alike letter, lower-case title on an unbranded page); engine verifies stray-marked money cells (`stray_marked_money`); **Merrick holder from the replaced text layer's labelled line** (`CARRY_LAYER_HOLDER`, `original_layer_holder`) |
| 3c7ae78b | Andrews row dates damaged only by OCR marks, read when the payment order fixes them (`ORDERED_DAMAGED_DATES`) |
| 5c99e3e1 | Andrews long credit-voucher payment: three more printings |
| c53e729f | Andrews quiet sections: Ending Balance date with a speck/look-alike equal to the printed period end; band check on label positions |
| a64c2a94 | Test expectation for the ending-date rule |
| (this) | Notes |

## Numbers (counts only)

### Whole truth set, final code c53e729f (frozen copy), `--readings` (wave-4 + fresh 7) — `fin-real/bench/r5ac-full`, REAL exit 0

Truth snapshot = the 567 documents / 1,408 periods of the bench of record (`tmp/r5ac/truth-full`; the shared truth has
since gained 16 Synchrony documents with no wave-4 reading). The bench of record rescored on the same snapshot
(`bench/r5ac-before`) gives exactly its recorded figures (1,034/1,237, 0 wrong), so before/after use identical truth.
Import 14.8 h on a shared host.

| | before (bench/wave4-a152, a15230a0) | **after (c53e729f)** |
|---|---|---|
| Ready without any edit | 1,034 / 1,237 (83.6%) | **1,072 / 1,237 (86.7%)** |
| Recoverable ready | 1,034 / 1,233 | **1,072 / 1,233** |
| Wrong admissions | 0 | **0** |
| Critical-field errors | 0 (13,804 rows / 1,044 periods) | **0 (15,371 rows / 1,082 periods)** |
| Must-hold kept out | 4 / 4 | 4 / 4 |
| Exact copies held | 148 / 151 | 148 / 151 |
| Previously ready periods lost | — | **0** (38 gained: andrews 31, merrick 7) |
| Batch items matched to no truth period | 37 (0 offered) | 22 (**0 offered**) |
| Admitted unscored (OCR-reconciled truth) | 10 | 10 (same periods) |
| Valid-looking wrong values proposed | 73 (amount 29, date 39, currency 5) | 69 (27, 37, 5), 0 in ready periods |
| Investigator actions, 567 statements (single / grouped) | 5,637 / 5,449 = 994 / 961 per 100 | **4,621 / 4,457 = 815 / 786 per 100** |
| Field edits / rows to add / decisions | 2,629 / 1,397 / 54 | 2,517 / 972 / 51 |
| Compare: periods + items without disagreement | 1,150 / 1,445 | 1,189 / 1,430 |

Per family (ready, actions single/grouped): andrews-share 200 -> **231**/270 (1,590/1,571 -> **607/595**); merrick-card
16 -> **23**/42 (106/68 -> **88/67**); credit-one 51/53, capital-one 117/119, citi 49/49 unchanged; every other family
unchanged. Blocking reasons (scored, overlapping) before -> after: reading 113 -> 90, balance 98 -> 75, holder 34 -> 23,
no_activity 16 -> 13, duplicate 9 -> 8, assignment 5 -> 4, not_detected 8 -> 9 (d892131891936#23: a quiet savings
section whose heading is unread in both runs; before, the harness paired it with an orphan page that was really an
April page cut off by a misread continuation notice, which now links to its own period d892131891936#22, now ready).
All ready periods library-served (no change in routing; the general engine was not touched).

### Neil's ruling 1 (Andrews verb misread)

- Rows decided by the rule: **7** (fresh readings; also 7 on the wave-4 readings), **7 equal to the verified truth**, 0
  wrong. Before: held by design.
- Periods unlocked: **4** ready now that were held: d730f3e0d171f#86, d730f3e0d171f#94, d1db0b3c9ca54#20 (rule alone),
  d1db0b3c9ca54#12 (rule + stray-marked cell). da162973a4fa0#14 and #23 had their verb rows decided but stay held for
  other cells.

### Neil's ruling 2 (card late-posted charges), measured on fresh reads of the 9 card documents (425 processor periods)

Truth rows dated before their billing cycle: Capital One 92, Citi 28, Credit One 4, Merrick 1.

| Rule | Capital One rows dropped (periods) | Credit One | Citi | Merrick |
|---|---|---|---|---|
| Dates only inside the printed cycle (old rule) | 92 (52 printed periods, incl. exact copies) | 4 (4) | 0 (own rule) | 0 (own rule) |
| a15230a0 (`card_row_dates` with posting/single-column anchors) | **0** | 1 (1)* | 0 | 0 |
| This unit (both dates before the cycle anchored by the posting date) | **0** | 1 (1)* | 0 | 0 |

\* Credit One d9a66ffec8137#32: its purchase date's slash was read as "1" (`dd1dd`), a different cause (see Decision
12). The extension changes no period in the truth set and dates no row the truth does not have (per-period comparison
identical; whole-set card families unchanged). The known live example (case 49494305, saved statement) is the
saved-statement path built by ec6fca0b; that path now accepts the new basis too.

### Root causes, Andrews (270 periods; before = 70 held on a15230a0, after = 39 held)

Primary cause per held period (estimator on the reader's rows, private `tmp/r5ac/andest*.txt`; benchmark reasons agree):

| Root cause | Held before | Fixed by | Held after |
|---|---|---|---|
| Disputed money cell the per-page pinned rule could not fix (first/last payment of a page, adjacent disputed cells, minus read as 2, stray-marked cells never crop-verified) | 24 sole / 37 any | period-wide pinned reading, propagation, minus support, stray-mark targets | 16 sole / 20 any |
| Continuation notice read with spaces/points (next pages not linked) | 5 | `_continued` | 0 |
| Page heading with a look-alike in the cycle / lower-case title (page not recognised) | 2 | continuation-only pages | 0 |
| Payment word misread (ruling 1) | 6 any / 3 sole | ruling 1 | 0 |
| Row date with specks / look-alikes | 11 any / 5 sole | dates in payment order | 3 any (letters for two digits, garbage) |
| Credit-voucher printings | 7 any / 3 sole | voucher variants | 1 (balance with a colon for the point) |
| Quiet section not proven (ending date speck/look-alike, tall money box) | 3 | quiet-proof fixes | 0 |
| Closed share sections (opening line then Closed, no ending line) | 3 | — | 3 |
| Running-balance mismatch / unlinked line | 4 | — | 4 |
| Duplicate / assignment / not detected (file structure) | 10 | — | 10 |
| Must-hold (expected) | 4 | — | 4 (kept) |

### Root causes, Merrick (26 held before, 19 after)

| Root cause | Before | After |
|---|---|---|
| Holder alone (image reading lost the coupon name) | 7 | **0** (all 7 ready; 11 of 42 statements now take the layer's labelled holder, 42/42 equal to truth) |
| Start date only (`merrick-card/dates`, no previous statement in the file or its balance unreadable) | 5 | 7 (#2 and #12 were holder + dates) — genuine grouped decision |
| Balance / reading / dates (Previous Balance disputed, payment minus unread, decimal point lost on amounts) | 14 | 12 |

### Synthetic (`fin-wt/bench-runs/r5-andrews-cards-final`, frozen c53e729f)

**105/125**, recoverable 105/108, 0 wrong, 0 critical (354 rows), holds 10/10, copies 1/1, 0 valid-looking wrong
values, exit 0. Andrews 43 (unchanged), Merrick 3/5, Credit One 7/10.

### Live ledger (read-only audit on the current live data, `fin-real/audit-r5ac`, READ ONLY transaction)

813 admitted live periods on truth documents: agrees 303, convention_only 412, **disagrees 6**, undated 91, no truth 1;
same printed period admitted twice: 0. The 4 known disagreements are unchanged; the 2 new ones are Synchrony card periods
(truth added by t-visual-v17 this wave), outside this unit's families. Live periods this unit would change on re-read:
only currently held Andrews/Merrick periods gain repairs; no admitted live period's reading changes (every change only
reads a cell, date, page or holder that was unreadable before). Nothing changes live until deploy + re-read (reading
revision v17; v16 digest b9248b80 added to the reader-recovery list).

## Decisions taken (each reversible in one place)

1. **Ruling 1** as Neil ruled: direction from the printed sign only when previous and new printed balances agree with
   it exactly; a misread word that still reads like one payment word keeps the existing sign/word conflict hold.
   Reverse: `statement_import_andrews.MISREAD_VERB_DIRECTION = False`.
2. **Ruling 2** extended to both dates before the cycle (posting date names one date in the 31 days before the cycle
   and anchors the purchase). Reverse the extension or the whole late-posted rule:
   `statement_layout_context.LATE_POSTED_CHARGES = False`.
3. **Whole-period pinned reading** (r3's recommendation): same rule as the engine's per-page pinned reading, over the
   period's controls across pages, only from stored printed readings, all or nothing per period, ending balance
   included. Reverse: `andrews_period_pinning.PERIOD_PINNING = False`.
4. **Pinned cells propagate** to neighbours in later rounds (adjacent disputed cells). Reverse:
   `statement_reading_quality.PROPAGATE_PINNED = False`.
5. **Minus read as 2 or +** by the crops supports the page reading as a candidate only. Reverse: drop
   `_minus_misread` from `_printed_readings`.
6. **Stray-marked money cells** (`·`, `_`, `°`, doubled point, ...) are crop-verified on Andrews pages; the
   interpretation is a candidate only. Reverse: the two `stray_marked_money` lines in `_target_kind`.
7. **Continuation notice** letters exact, spaces/points/middle dots ignored (superset of the old substring check).
8. **Continuation-only pages** (cycle letter look-alike, lower-case title without brand mark) only continue a
   statement with identical account and dates. Reverse: drop the two fallbacks in `andrews_page`.
9. **Row dates read in payment order** (0 of 6,465 verified Andrews rows out of order). Reverse:
   `ORDERED_DAMAGED_DATES = False`.
10. **Voucher label cell holding amount and balance** is read from page text only because both running-balance checks
    (its own and the next line's, crop-checked) must hold.
11. **Merrick holder carried** from the replaced layer's `Send Payments to:` line, same account only. Reverse:
    `statement_import_merrick.CARRY_LAYER_HOLDER = False`.
12. Not done on purpose: a backend reading of card dates whose slash was read as "1" (`04114`) beside an exact other
    date. It recovers Credit One #3 and #32 on the readings, but two existing tests encode the decision that such a
    date is left to the engine's own-cell reread and counts as unreadable when choosing the image reading; changing it
    would also change which reading the engine keeps on Credit One pages (51 ready). Reverted, left to Neil/next unit.

## Tests actually run

- Backend targeted while building (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1): statement_import_andrews,
  andrews_scan_layouts, andrews_period_pinning (new, 8), andrews_pinned_reading, andrews_no_activity, statement_import_merrick,
  statement_layout_context, late_posted_card_dates, statement_import_card, statement_import_credit_one, card_split_columns,
  card_summary, statement_information, exports, recovery_readers (pytest 18) and the 22 statement_import* /
  review_checks / reading_quality modules (345 OK).
- Evidence engine (OMP_THREAD_LIMIT=1), 18 modules (money verification, Andrews pinned/scan cells, pdf_extraction,
  native/amount/date OCR, Merrick, card cells, second reader, glyph reader, unread lines, scan preparation, BBVA/Capital
  One cells): **420 passed**. `test_pdf_worker` not run (known sandbox failure).
- Full financial suite once on the final code: **Ran 6,015, failures=3, skipped 20** -> the 2 known
  `test_financial_unassigned_statement` failures plus one expectation of mine (`test_financial_statement_information`,
  the damaged ending date now reads as the period end), fixed in a64c2a94 (module OK after the fix).
- Frontend: not touched, not run.

## Not verified / caveats

- The whole-set run used wave-4 readings for 560 documents. The engine changes (printed readings stored for held
  cells, minus-as-2 support, stray-marked targets, page recognition via the reader) can only act where a pinned record
  exists (Andrews, Credit One, Merrick: all 7 re-read fresh) or on Andrews pages; other families' held cells only gain a
  stored field. Not re-measured with a fresh read of the other 560 documents.
- Census not re-run (cached readings of an older engine cannot show engine changes).
- The UI does not yet show the period-pinned cells (`value_repairs`) beside the machine reading; the rows carry the page
  reading, held text, accepted reading and pinning cells, like earlier pinned repairs.
- The whole-period pass recomputes the Andrews proposal once per candidate reading; on the largest period (6 pages,
  ~180 rows) it stays well under a second here, not profiled further.

## What the next unit should continue

1. Andrews residue (35 recoverable held): disputed money cells with no printed reading the controls can pin (crop
   readings that disagree with each other and the page, e.g. a joined cell whose crops insert a dash) 16 sole; closed
   share sections (3: prove quiet closure in `andrews_no_activity_evidence` and let admission accept a closure without a
   closing row, `statement_admission.closure_without_closing`); a balance with a colon for the decimal point (1, engine
   target); dates with two damaged digits (3); duplicate/assignment structure (10).
2. Merrick (19): a disputed Previous Balance equals the previous statement's confirmed New Balance (a second printed
   fact): plumb that agreement from `closing_only_period` into the proposal's opening row (fixes the start-date hold
   `balance_unreadable` too); amounts whose decimal point was lost (`123` read for 1.23) and payment minus unread follow.
   The 7 start-date-only periods are a genuine grouped decision (`merrick-card/dates`).
3. Credit One #3, #32 (see Decision 12) and Capital One df9292c6e6c36#17, #18 (no_activity), not attempted.

## Decisions needed from Neil

- None blocking. Decisions 1-11 are each reversible in one place. Decision 12 (card dates whose slash reads as "1")
  was left as it is because existing tests encode the opposite choice; a ruling would settle it: recommendation is to
  keep it with the engine's own-cell reread (Credit One 51/53 already).

## Privacy

No real value in any commit message, code comment or test; test values are synthetic (privately scanned against the
truth amounts, holders, accounts and file names: only coincidental small round synthetic amounts). Notes, commits and
this file hold counts and opaque ids only.

## Private paths (not in git)

- Runs: `fin-real/bench/r5ac-full` (whole set, final), `bench/r5ac-before` (bench of record rescored on the same
  snapshot), `bench/r5ac-run1` (fresh engine read of the 7 documents; import stopped after the read).
- Readings: `tmp/r5ac/full-readings.json` (merged), `bench/r5ac-run1/engine-readings.json`; replays `tmp/r5ac/rp-*.json`.
- Truth snapshots: `tmp/r5ac/truth-full`, `tmp/r5ac/truth-mini`. Live audit: `fin-real/audit-r5ac`.
- Tools: `tmp/r5ac/{dev,andest,andall,tally,replay,pindiag2,perdiag,pinpage,r1check,datecheck,vouchcheck,dates,quiet,cards,c1row,merest,merholder2,privscan}.py`.
- Frozen code copies: `fin-wt/bench-code/r5ac-39a45f8f`, `fin-wt/bench-code/r5ac-c53e729f`.
