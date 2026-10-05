# r1-reproduced — WIP notes (real-document phase, wave 1). Unit complete.

Counts and opaque ids only (d + original sha256 prefix, #n = statement). Private detail under /mnt/owl-data/fin-real
(bench/r1-reproduced, bench/wave0-r1, census-r1, audit-r1, tmp/r1). Nothing live was written; nothing pushed.

## Landed (branch fin/r1-reproduced, base 6b812436)

- 7b00e2f3 processor: copies across files, reprints inside a file, pre-cycle card rows, invisible-text origin rule,
  synthetic tiled-OCR corpus case, engine reading revision v14 (+ wave-5 pdf_extraction digest in AFFECTED_EXTRACTION_SHA256)
- e0fda7cd review group "Statement printed twice in one file"; duplicate panel names the new matching details (frontend)
- 3d2878f1 fix: compare the whole printed reference (letters too), not only its digits (caught by the B-gate tests)
- c98f48bf misread audit measures the original with the current origin rule
- (this commit) WIP-NOTES.md

## What changed in the processor

1. **Copies across files** (`pending_statement_duplicates`, `statement_import_overlap.same_printed_period`). Root cause:
   a card prints 4 digits, so its identity is masked and `same_statement` (full reference + equal holder) never matched;
   the copy was only a non-blocking "overlap". Now: same printed reference (leading mask removed, letters and digits
   equal), currency, product and exact dates nominate a copy, holder not compared; equal payments (amount, direction,
   date multiset) and equal printed balances set the later copy aside, linked to the retained one (basis
   `identical_financial_reading`, matched_fields incl. `payments_and_balances`). Also when the bank name was read
   differently (then at least one payment is required). Different money: held (coverage review now calls the exact
   masked period a matching statement, which blocks import). Byte-identical copies still need the same source section.
   **Decision (reverse in one place):** equal money = duplicate even with other wording/holder; reverse by requiring
   `same_reading` instead of `same_money` in `apply_duplicate_disposition`.
2. **Reprint inside one file** (`statement_import_catalog._capital_printings`, `statement_import._printed_copies`,
   `import_batches.assess`). A Capital One cycle whose printed "Page 1 of N" restarts is a second printing: its own
   period, linked to the first (first keeps its id). Equal money: reprint set aside as a copy of the first printing
   (`printed_copy` decisions stay valid whatever the first printing's own outcome). Different money or an edited
   reprint: every printing held (new review group "reprint") until a person records why one is imported. Unread page
   counts never split (status quo: doubled rows refused by the balances).
3. **Purchase before the cycle** (`statement_layout_context.card_row_dates`). One-date card table: month/day resolved to
   the single date in the 31 days before the cycle (basis `printed_before_cycle`); balances must still reconcile.
4. **Invisible text** (`suspect_amounts.page_text_origin`, used by backend AND engine — the engine imports it, no
   separate engine rule exists). >50% of a page's characters drawn in render mode 3 = recognised text whatever the
   image coverage. **Decision (reverse in one place):** `INVISIBLE_TEXT_SHARE` check in `page_text_origin`.

## Before / after (real benchmark, verified truth, same frozen manifest for both)

The truth manifest changed during wave 1 (t-visual-v10 added Andrews visual truth: 1029 distinct verified periods, was
761). wave 0 (code e07ff7bd) and this branch were both rescored against one snapshot (tmp/r1/truth-snap, manifest
sha256 1865b894d0fc5e53). This run reused the wave-0 engine readings except the 3 documents whose page verdict changes
(fresh engine reads: text and geometry identical, only 6 page-origin labels changed).

| | wave 0 (e07ff7bd) | r1-reproduced (c98f48bf) |
|---|---|---|
| Ready without edits (1029 distinct) | 585 | 585 as scored; **586 actual** (see pairing note) |
| Exact copies held automatically | 3 / 145 | **99 / 145** |
| Copies offered / imported | 95 / 95 | **0 / 0** |
| Repeated ledger rows across statements | 941 | **0** |
| Harness "duplicate ledger contributions" | 1,695 | 788 (≈785 are identical same-day rows inside one statement) |
| Wrong admissions (scored) | 2 | 2 (the same pre-existing item, see below) |
| Critical-field errors | 0 | 123 (all that same item, paired to a different truth twin) |

- **Copy residue 46 = dacb853f7b7ec (copies of d9b89251845be), Citi: not detected at all** (no Citi reader; unit
  r1-monex-citi). Once detected they go through the same rule; the integrator should confirm after that merge.
- **No distinct period lost:** every original of a set-aside copy is ready; no verified period moved ready -> not ready.
- **Pairing note (harness, not processor):** d22e405327ccf#12 (verified) is ready and imported with 2/2 rows correct,
  but the scorer attached the set-aside reprint item to #12 and the ready first printing to #13 (the truth's own
  duplicate of #12, unscored). Fix candidate for the harness: prefer page overlap when pairing items of one file.
- **Pre-existing wrong admission, not this unit:** d0f81a5b856d7 (Andrews, new visual truth): #13 (hold) admitted, and
  the share-0040 November item (0 rows read) admitted; the truth has twins #12 (auto, 123 rows) and #14 (hold, 0 rows)
  with identical share and dates, so the scorer pairs it to #14 (wave 0) or #12 (here). Same reading, same readiness
  at wave-0 code. For the Andrews / visual-truth work.
- Targets 2 and 3 (truth ids): d22e405327ccf#12 and #2 now ready, rows saved 2/2 and 7/7 (the pre-cycle purchase
  included); df7e9c5f8cbb0#12/#2 and both reprints set aside. (#2 truth is ocr_reconciled, unscored.)
- Synthetic (bench-runs/r1-reproduced-synth, code 3d2878f1, BENCH_EXIT=0): **103/125**, recoverable 103/108, 0 wrong,
  0 critical; the original 124 periods unchanged at 102/124; the new tiled case is ready (page recognised, image
  re-read, every money cell confirmed; the old rule called it born-digital at 18.5% coverage).

## Invisible-OCR rule (item 4): what it actually touches

- Measured on every original: **4 originals / 60 pages** change verdict (d9a66ffec8137 54, df7e9c5f8cbb0 3,
  d624d41045389 2, d22e405327ccf 1). r-census's "7 originals / 145 pages" counted every engine-native page of files
  that had any invisible page; the other invisible pages are already full-page rasters.
- Real benchmark (verified): 3 documents, 6 pages, **0 periods change readiness** (crop verification confirmed every cell).
- Census case 49494305: **10 periods of d9a66ffec8137 move ready -> held** (not in verified truth). Attributed by a
  rule-off read of the same engine (private copy of the tree): rule-off geometry == old reading; rule-on changes 101
  money cells (r-census had found 89 disputed cells on this document). Correct hold, not a regression.

## Live (read-only) and census for case 49494305 (item 5)

- Live ledger audit rerun (audit-r1): 102 printed periods admitted twice (all in 49494305: 52 d22e405327ccf +
  df7e9c5f8cbb0, 50 d568d90faff56 + d624d41045389; the earlier 107 came from the 07:03 truth snapshot); 5 disagree
  (unchanged, live untouched).
- **New code would have set aside 102 / 102 of the live double admissions**: for every printed period exactly one copy
  stays importable (d22e405327ccf / d568d90faff56 retained, df7e9c5f8cbb0 / d624d41045389 set aside).
- Census (census-r1, code 3d2878f1): ready 143 -> **239** of 581 periods; "overlap" hold 226 -> **0**; 105 periods set
  aside as duplicates, 104 of them admitted live. 2 file errors (table over review limit) pre-existing and unchanged.
- Misread audit with the rule (audit-r1 under census-r1): native-only skips 102 -> 50; **52 more live reviews audited**:
  51 of d624d41045389 all consistent (every money cell agrees), 1 of d9a66ffec8137 with one cell now disputed
  (flagged 16 -> 17; a person should look, not a demonstrated misread).

## Tests actually run

- New/updated (synthetic fixtures only): pending duplicates (+5 incl. holder/bank read differently, masked copy
  differing money held, printed reference with letters), overlap fixture (revised copy now differs in money),
  B-gate fixture (same), statement reprints (3, end to end through read/assess/disposition/import), catalog (+3),
  layout context (+4), suspect amounts (+5 incl. a real tiled PDF), misread audit (+1).
- Financial suite (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1) at 3d2878f1: **Ran 5760, failures=2** (known
  unassigned_statement), skipped 20. Was 5740 on base. c98f48bf touched only the audit script: pytest misread audit +
  census 14 passed. batch_review_summary + reprints 9 OK.
- pytest test_financial_recovery_readers 18 passed (digest list).
- Frontend: StatementDuplicateDecision.test 13/13, `tsc -b` 0, eslint on the changed files 0. Full vitest not run.

## Unverified / limits

- Citi copies (46) untested until a Citi reader exists.
- Bank-name-read-differently path is proven on synthetic data only (no real pair needed it: every real pair read the
  same bank and holder).
- Hold message "A separate file matches this bank, full account, holder…" is now also shown for masked card copies,
  where "full account, holder" is inaccurate. Left unchanged (pinned by financial_legacy_batch_read).
- The real run reused wave-0 readings (engine code identical apart from the origin label path); not a fresh full read.

## Next unit should

1. After r1-monex-citi merges: rerun the real benchmark, confirm the 46 Citi copies are set aside (target 145/145).
2. Harness: pair items of one file by page overlap (in-file reprints, Andrews twins) before scoring.
3. Andrews: d0f81a5b856d7 November share 0040 item read 0 rows yet ready (123 printed rows) — a wrong admission under
   the new visual truth, present at wave-0 code too.

## Decisions needed from Neil

1. **Live double admission, case 49494305 (102 printed periods).** The new code keeps d22e405327ccf and d568d90faff56
   and sets aside df7e9c5f8cbb0 and d624d41045389. Recommend removing the 102 live periods of those two copies through
   the product's removal path after deploy. Not touched.
2. **Deploy together** (engine + backend, reading revision v14). With `LOUPE_FINANCIAL_READER_RECOVERY` on, readings made
   by the current release become eligible for the re-read sweep (wave-5 digest now in the affected list, per protocol);
   that re-read is what brings crop verification to the 4 live originals above.
