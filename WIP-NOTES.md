# r8-mt-engine: M&T statements read by the general engine (counts and opaque ids only)

Branch fin/r8-mt-engine (base fin/release-1 d5985a0a). Not pushed, not merged. Private detail (dev tools,
surveys, per-statement comparisons, frozen code, renders) under /mnt/owl-data/fin-real/tmp/r8m/; runs under
/mnt/owl-data/fin-real/bench/r8m-*; logs /mnt/owl-data/fin-real/logs/r8m-*.log.

## Landed (commits)

| Commit | What |
|---|---|
| 7c215ef1 | Evidence engine, reading revision **v20**: on vector-text pages a printed line page OCR skipped altogether is read from its own crop (whole lines only, confidence >= 60, at most 40 a page); the outline record carries `lines_read`, `lines_checked`, `lines_unread`; a figure token whose narrow characters stand a space-wide bearing apart is re-read one character per outline; a page drawing >= 300 character outlines over an image covering most of it is vector text. |
| edef841b | General engine: addressless holder (switch `statement_engine.ADDRESSLESS_HOLDER`); a bank's bare name heading a postal block marks the issuer's own address; a logo/heading institution must be printed twice and never replaces a matched profile's issuer; profile matching ignores dated lines when several profiles match; credit line mailed inside a deposit statement (another account's page starts its own statement, mailing-wide page numbering, summary printed as a table, dated line under its own section heading, vocabulary); document day-month order for ambiguous periods and dates; money-sign head + lost thousands comma; 4-digit account after a full account-number label; v19 pdf_extraction digest added to the reader-recovery list. |
| 8d987ab8 | Fix found by the whole-set survey: only another account's statement shares its mailing's page numbering (a continuing-numbering rule had let 2 Monex sections of one numbered statement prove with no truth period; they are held again). Regression test. |
| (this commit) | WIP-NOTES.md |

No M&T-keyed code: M&T keeps only its existing institution profile (data). No library reader added.

## Root causes found (from source and the readings)

1. Holder (65 periods): the production redacts the address, so `address_holder` (postal-line anchored) never
   fired. On 25 documents page OCR had also **lost the first name line** (Tesseract layout analysis skipped
   it), so a naive addressless rule would have read the second joint holder (holder_differs): fixed in the
   reading (v20 line recovery) and guarded in the rule (no holder next to a printed line still unread).
2. Rows unread (19 periods): OCR read every date with two 1s as '4x/..' (the two narrow 1s stand a
   space-wide side bearing apart, so the outline re-reading refused the word); 6 pages were classed as scans
   because a shaded background image covers most of the page; one text-layer page lost a thousands comma.
3. Line of credit (6 distinct periods): merged into the deposit's segment when it printed the same period;
   period dropped when both day-month orders were valid; summary printed as a table not read; the dated
   INTEREST CHARGED line taken as a summary component; 4-digit account refused; remittance block's
   department line taken as holder.
4. Institution: the logo was read as another bank's name on 14 periods (it blocked nothing only because the
   holder blocked first); the M&T profile did not match 4 documents because a movement line named a card
   issuer (two profiles matched -> none).

## Decisions (each reversible in one place)

1. **Addressless holder corroboration** (`_addressless_holder`, switch `ADDRESSLESS_HOLDER`): one to three
   name lines at one left edge, left half of the first page, above the movements, nothing else at that edge
   directly below; plus a second printed fact: a mailing line of figures alone directly above at the block's
   edge, or the top line reprinted as a whole line on the statement (header / coupon); plus the page's
   reading checked its printed lines and none near the block is unread (pages without the v20 check never
   use the rule); all such blocks name one holder. Reverse: `ADDRESSLESS_HOLDER = False`.
2. **Institution**: a second-tier (logo/heading) name needs two printed lines; a matched profile's issuer
   replaces a differing read. Reverse: drop `pages` from the `_institution` call / the `_same_issuer` branch.
3. **Mailed statements**: only a page labelling its own period and only accounts not yet printed under a
   full account-number label starts a statement mailed with the previous one (numbering checked over the
   mailing). A continuing page number alone is NOT enough (Monex finding). Reverse: `_other_account_statement`.
4. **No-activity money-market periods (3) stay held** for the existing no-activity confirmation: the M&T
   summary box splits interest and service charges out of its "deposits"/"debits" lines, so reading those
   labels as totals would break the proved interest-bearing periods. Not M&T-coded; not done.
5. Reader recovery: the v19 file digest (8f3539f3) added (as instructed); v18 digests were not in the list
   before and are not added (never deployed).

## Measured

### M&T (mt-bank: 85 documents, 90 distinct verified periods + 2 duplicates)

| | bench/wave7 (v19, 0c112612) | **this unit (v20 readings, 8d987ab8)** |
|---|---|---|
| Ready without any edit (whole set run) | 0 / 90 | **87 / 90** (all 87 saved by the system) |
| Engine-served / library-served | 0 / 0 | **87 / 0** |
| Generic-only (`LOUPE_FINANCIAL_GENERIC_ONLY=1`, mini corpora, same readings) | 0 / 90 | **87 / 90** (v15 40/41, v16 47/49; no family reader exists, so identical) |
| Rows of ready periods equal to truth (date, amount, direction) | - | **879 / 879** (0 missing, 0 extra, 0 differing) |
| Holder / institution on ready periods | - | holder present on 87/87 (86 printed, 1 from the existing same-account detail proposal, equal to truth); institution M&T on 87/87; **0 holder_differs, 0 institution differs** |
| Duplicates (d8b425ad12475#1/#2) | unread | **held as linked exact copies 2/2**, 0 offered, 0 saved |
| Wrong admissions | 0 | **0** |
| Investigator actions (single / grouped) | 890 / 720 | **9 / 7** |

Held 3: the no-activity money-market periods d1dcbc0d7a5a1#1, dc29d561ddfc0#1, de6232328a347#1 (no movement,
opening = closing; held for the existing no-activity confirmation, grouped as one mt-bank/no_activity
decision). Engine survey on the v20 reading (private, sv.py): 89/92 proved, 88/92 with every field and row
equal to truth, 0 proved with any field differing; the one proved period without its own holder
(d3df70b5f4085#1, a page with the producer's text layer, which records no printed-line check) is saved with
the holder of the same account's saved statements by the existing detail proposal.

By class from the prompt (65 + 19 + 6 = 90): holder-only 65 -> **65** ready (addressless rule); rows/balances
19 -> **16** ready (15 with their printed holder, d3df70b5f4085#1 with the detail-proposal holder; the 3
no-activity periods stay held); line of credit 6 distinct (+1 duplicate) -> **6** ready, holder from the
window block reprinted in the page header and coupon, never the remittance block.
Institution read as another bank: 14 -> 0 (logo names printed once are not read; the profile's issuer wins).
Line-of-credit periods not detected 2 -> 0 (whole set not_detected 4 -> 2, the 2 left are wave 7's Andrews
and Santander ones).

Mini corpora (fresh v20 read of all 85 documents via the harness's own engine_read, then `--readings`):
truth-mini-v15 40/41, 0 wrong, exit 0; truth-mini-v16 47/49, 0 wrong, exit 1 only because its 2 duplicate
periods' originals are in the v15 shard (alone in that corpus they are the only printing; t-visual-v16 noted
the same); combined M&T corpus (both manifests, private tmp/r8m/truth-mini-mt) 87/90, 0 wrong, copies held
2/2, exit 0.

### Whole real set (bench/r8m-whole668: frozen 8d987ab8, product default, the 668 wave-7 documents)

Readings: bench/wave7's, with fresh v20 readings for the 134 documents the engine change can touch (85 M&T +
49 other documents with vector-text pages; every other page reads identically) merged into a copy
(bench/r8m-whole-readings.json). Corpus: the shared truth manifest filtered to the same 668 documents
(1,516 truth periods, as wave 7; the shared manifest now has 703 documents from the concurrent t-visual-v05).
Compare written to a private dir (tmp/r8m/compare-whole), not the shared compare/.

| | bench/wave7 | **r8m-whole668** |
|---|---|---|
| Ready without any edit | 1,147 / 1,343 (85.4%) | **1,236 / 1,343 (92.0%)**, all saved by the system |
| Recoverable ready | 1,147 / 1,339 | **1,236 / 1,339 (92.3%)** |
| Wrong admissions | 0 | **0** (REAL_EXIT=0) |
| Critical-field errors in saved rows | 0 (17,948 rows) | **0 (18,835 rows from 1,246 periods)** |
| Must-hold kept out | 4/4 | **4/4** |
| Exact copies held automatically | 148/153 | **150/153**; offered 0, **saved 0** |
| Previously ready lost | - | **0** |
| Gained | - | **89**: mt-bank 87, intercam-mexico 2 (wave 7 scored these 2 while their readiness was still refreshing in the background: STATE's measurement gap, not this unit) |
| Valid-looking wrong values proposed | 5 | **4, 0 in ready periods** |
| Batch items matched to no truth period | 16 (0 offered) | **16 (0 offered)** |
| Engine-served / library-served ready | 110 / 1,037 | **197 / 1,039** |
| Investigator actions, 668 statements (single / grouped) | 2,094 / 1,840 = **313 / 275 per 100** | **1,184 / 1,098 = 177 / 164 per 100** (field edits 989 -> 283, rows to add 468 -> 386, decisions 36 -> 36) |
| Compare: statements / periods+items / without disagreement | 668 / 1,532 / 1,291 | **668 / 1,532 / 1,381** |
| Classes in ready periods | holder_differs 26 (BBVA) | **holder_differs 26 (BBVA, unchanged), holder_missing 1 (the M&T detail-proposal period)** |

Per family (ready before -> after; engine / library): bbva 363 -> 363 (30/333), andrews 231 -> 231
(0/231), monex 200 -> 200 (29/171), capital-one 117 -> 117, **mt-bank 0 -> 87 (87/0)**, santander 36 -> 36
(27/9), credit-one 51 -> 51, citi 49 -> 49, intercam 39 -> 41 (0/41), merrick 23 -> 23, kapital 17 -> 17,
synchrony 16 -> 16, scotiabank 5 -> 5. Lost 0 in every family.

### Holder rule (and every engine change) measured on every family

- Private engine survey of all 668 documents (base d5985a0a vs this code, wave-7 readings): outside M&T
  nothing changed in holder, institution, currency, account or balances; the only other change is Citi
  (library-served): the engine now separates more card cycles in 2 multi-cycle files (document date order),
  4 more proved, all 4 equal to truth. The survey also caught the continuing-numbering rule letting 2 Monex
  sections prove with no truth period (fixed in 8d987ab8; re-surveyed: gone).
- The 49 non-M&T documents re-read at v20, branch code vs base code on their wave-7 readings: **no change at
  all** (holder, institution, rows, proof).
- So the addressless rule newly proves holders in **mt-bank only** (every M&T deposit and credit-line
  period); 0 in every other family; it changes no ready period's holder. Santander's 15 holder holds are a
  different cause (a barcode printed over the postal-code line, address present): untouched.


## Tests actually run

- Engine: `tests.test_financial_statement_engine` **155 OK** (21 new, synthetic only: addressless holder 8,
  issuer address 2, logo institution 3, mailed credit line 5 incl. the Monex-shape regression, scan damage 3).
- Evidence engine: test_vector_glyph_reading + test_pdf_extraction + test_unread_printed_lines +
  test_pdf_text_origin **77 passed** (3 new).
- Touched-area backend modules (recovery_readers, statement_import_merrick, exports, candidate_*,
  engine_reading_cache, pdf_*candidates): **484 passed**.
- Full financial suite (CLAUDE.md command, live .venv, CHROMADB_PORT=1 CHROMA_PORT=1) on 8d987ab8:
  **Ran 6,369, failures=2, skipped=20, errors 0**; the 2 = test_financial_unassigned_statement, which fail
  identically on the base code (d5985a0a archive), as STATE.md records.
- Synthetic benchmark (frozen 8d987ab8, product default, fresh read): **105/125**, recoverable 105/108,
  0 wrong, 0 critical (354 rows), holds 10/10, copies 1/1, all 105 saved by the system, **BENCH_EXIT=0**
  (bench-runs/r8-mt-engine-final).

## Next units should continue with

- Santander holder holds (15 periods, the largest holder block left): the addressee block prints a full
  address whose postal line a barcode overprints ('C.P. ... C.R. ...'); a reader of the postal line through
  the barcode (or the fiscal-receipt / reprint corroboration) is the next holder unit.
- M&T no-activity periods (3): would need a no-activity proof from the printed summary counts ('NO. 0') or a
  section-aware summary box; one grouped confirmation clears them today.
- Text-layer pages have no printed-line check, so the addressless rule never applies to them (1 M&T period
  needed the detail proposal). An equivalent check for embedded layers would extend the rule.
- Integration: reading revision v20 means live sources gain only when re-read; the whole-set figure above
  used fresh v20 readings of the 134 touched documents.


## Decisions needed from Neil

None blocking. Recommendation recorded as decision 1 above (addressless holder corroboration; switch
`ADDRESSLESS_HOLDER`). Reverse in one line if Neil wants redacted-address statements to wait for a person.
