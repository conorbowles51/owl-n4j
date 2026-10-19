# WIP notes: r10-engine-residue

Branch `fin/r10-engine-residue`, based on fin/release-1 f2b80e45. Counts and opaque ids only; everything
real lives under /mnt/owl-data/fin-real/ (bench dirs `bench/r10e-*`, tools, compare dirs and logs under
`tmp/r10e/`).

## Landed (5 code commits)

| Commit | Item | What |
|---|---|---|
| 57060073 | 1, 3 | General engine. (a) A summary box (balances and printed totals, no movement) that repeats every fact of the one proved section of the same printed account, period, currency and convention joins that section instead of standing as an unproved period of its own (`SUMMARY_BOX_MERGE`). (b) A date glued to the next word by a mark or with no gap is split off (`UNGLUE_LEADING_DATE`). (c) A first-in-line amount box widened by a margin mark is placed by its left-anchored width when its own band would be a phantom column (`WIDE_AMOUNT_BOXES`); a trailing run of em dashes is a rule tail. (d) Holder: a line continuing the issuer's block is not the holder; company names with letter+digit words are allowed for unanchored holders. Routing: a library row outside the engine scope may only be page furniture (no amount, no date). |
| 61c0f901 | 2, 3 | Routing. When both readers read a period alike, the engine serves it (under the library id) where only it establishes a fact from the period's own printed lines: a currency printed in the section or under the statement's single currency label where the library read none, or, for a period without movements, the generic printed-zero-totals proof (`AGREEMENT_PREFERS_ENGINE`). |
| f6d0cb32 | defect fix | A merged summary box keeps its own scope entries, and routing's own-scope trim keeps each recorded entry. Before: on a page printing box A, box B, table A, account A's import region crossed box B, and saving account B was refused as "already has imported transactions" (9 statements in the generic-only run on 61c0f901; refused, never saved twice). Found by the whole-set generic-only run. |
| 73f56473 | 2 | An agreed period the engine serves keeps the library's printing of institution, account reference and holder (they already agree by the identity check), so it reads like the account's other saved statements. |
| fc97f6f1 | 3 | Routing. A library period whose opening balance is an unreadable mark pairs with the engine section of the same printed account and period by an equal printed closing balance (`UNREAD_OPENING_PAIRS_BY_CLOSING`); before, the unread opening counted as "a different section" and the quiet period stayed with the unproved library reading. |

No evidence-engine change: the reading revision is not bumped and the wave9 readings are used unchanged.

## Measurements

Bench of record = the 728 documents of bench/wave9 with their truth (`tmp/r10e/truth-w9`, a symlink subset of
`truth/`; the manifest entries of those 728 are byte-identical before and after the v01 shard integration at
16:44, which added 26 documents that have no wave9 reading). Readings: a copy of
bench/wave9/engine-readings.json, unchanged. Each run at concurrency 1.

Product (default routing, compare dir `tmp/r10e/cmp-whole4`, code fc97f6f1; an intermediate run on 61c0f901 is
`bench/r10e-whole`):

| | wave9 | 61c0f901 | r10 final (fc97f6f1) |
|---|---|---|---|
| Ready distinct periods | 1315 / 1436 | 1331 | **1332** (target 1335: not met, 3 short) |
| Wrong admissions / critical-field errors | 0 / 0 | 0 / 0 | 0 / 0 (20933 transactions saved) |
| Ready periods lost vs wave9 | | 0 | 0 (17 gained, all Santander) |
| mt-bank / Santander / Monex ready | 87 / 111 / 204 | 87 / 127 / 204 | 87 / **128** / 204 (Santander target 125: met) |
| Statements saved, engine / library | 227 / 1099 | 407 / 935 | 416 / 927 |
| Santander saved, engine / library | 53 / 59 | 79 / 49 | 88 / 41 |
| Held for currency (scored periods) | 12 | 7 | 7 (target 3: not met) |
| Held for no activity | 11 | 10 | 9 |
| Human actions single / grouped | 1595 / 1519 | 1250 / 1180 | **1247 / 1177** |
| Per 100 statements (728) | 219 / 209 | 172 / 162 | **171 / 162** |
| Santander actions single / grouped | 757 / 734 | 412 / 395 | 409 / 392 |
| Exact copies offered/saved | dcfc8ce1f2afc#1 only | same | same |
| Saves refused as already imported | 0 | 0 | 0 |

(The unit's "currency-held 11" counts a little differently; with one rule applied to both runs it is 12 to 7.
The 7: six listed under Next unit plus one Andrews period, d892131891936#23, out of scope.)

Generic-only (`LOUPE_FINANCIAL_GENERIC_ONLY=1`, compare dir `tmp/r10e/cmp-gen2`, code f6d0cb32; the two later
commits change only engine/library routing, which generic-only does not use):

| | wave9-generic-only | r10 |
|---|---|---|
| Ready distinct periods | 896 / 1436 | 964 / 1436 |
| Wrong admissions / critical-field errors | 0 / 0 | 0 / 0 |
| Ready periods lost | | 0 (68 gained, all Santander) |
| Exact copies offered/saved | dcfc8ce1f2afc#1 only | dcfc8ce1f2afc#1 only |
| Human actions single / grouped | 5478 / 5196 | 4075 / 3862 |
| Per 100 statements (728) | 752 / 714 | 560 / 530 |
| holder_differs in ready periods | 2 | 2 (the same two, d16ceb8770641#1, dac6c1cdc6525#1) |
| Saves refused as already imported | 0 | 0 (9 on 61c0f901, fixed in f6d0cb32) |

Synthetic benchmark (`bench-runs/r10-engine-residue-final`, code fc97f6f1): exit 0, 108 / 125, 0 wrong,
0 critical-field errors, held kept out 10/10.

Tests:
* Full financial suite on fc97f6f1, run twice: 6483 tests, 2 failures (the two pre-existing
  `test_financial_unassigned_statement` failures), 20 skipped. The first run also had 1 error in
  `test_financial_checkpoint_b_gate` (`test_independent_edits_to_different_statements_and_batches_are_all_kept`:
  the second batch's item for a shared file not found); it passed 3/3 alone and in the second full run, and in
  the full run on 61c0f901 (6478 tests, the same 2 failures). Flaky, not investigated further.
* Engine test file: 202 OK. Routing/import/catalog test set (15 files): 441 OK.

## Per item

* Item 1 (Santander vector-text rows and balances): 111 to 128 ready. Root causes fixed in the engine: the
  page-1 summary box read as its own unproved period (so routing could not cover page 1), dates glued to the
  folio, margin marks joined into amount boxes or read as text, holder taken from the issuer block or
  rejected for a digit in a company name. Engine survey of the 18 item-1 documents: proved 16 to 24, proved
  with no hold 8 to 18, proved but wrong 1 to 0. The rest are listed under Next unit.
* Item 2 (currency held although printed): 12 to 7. Gained: dec355946865b#1/#2, db81fa7b3efaf#1/#2,
  d41406d5f952c#1 (the engine reads the printed currency, and routing now lets it serve the agreed period).
* Item 3 (zero-activity sections): 11 to 9 held. d41406d5f952c#2 and d96fb96106d3c#2 are ready (summary
  box merged with its detail; agreed quiet period proved by the generic printed zero totals; unread library
  opening paired by closing). The other 9: 4 BBVA card cycles whose payments line is unreadable (held by
  decision), 2 Capital One (card components, see Next unit), 3 Andrews (out of scope).
* Item 4 (Scotiabank 3, kapital/mt-bank 3): not done; findings under Next unit.
* Step removal: human actions 1595 to 1247 single, 1519 to 1177 grouped (219 to 171 and 209 to 162 per 100
  statements); Santander alone 757 to 409.

## Safety

* 0 wrong admissions and 0 critical-field errors in every run (product, generic-only, synthetic).
* Exact copies: only dcfc8ce1f2afc#1 (offered and saved, counted twice by the harness, the same as wave9).
  Exit status 1 of every real run is that copy.
* Classes in ready periods: no account, money, date or currency class in any run. `holder_differs` appears
  in ready BBVA periods in wave9 too: 26 in wave9 (rebuilt by rescoring a copy of the wave9 run directory
  with the wave9 code into `tmp/r10e/cmp-w9base`, because the default compare dir was overwritten by another
  run), 26 here, exactly the same 26 periods (20 on 61c0f901; 73f56473 returned the 6 to the library's
  spelling, which is what wave9 saved). holder_missing: the same 6 in both. They are the bank's printed legal-form punctuation
  against the truth spelling (or one OCR-lost space); the unit's "no holder_differs in a ready period" is
  therefore not met at baseline either. Not changed here.

## Incident (needs the owner's attention)

At about 16:27 UTC on 2026-10-18 I killed pid 802433, which was another session's harness
(`--out /mnt/owl-data/fin-real/bench/rguard`, the layer-guard benchmark, about 9 minutes into its run), while
stopping my own benchmark with too broad a match. Nothing else was touched. That rguard run must be rerun
by its owner. Afterwards my own processes were found only by their exact `--out bench/r10e-<label>`
(`tmp/r10e/mypids.sh`). Details in `tmp/r10e/INCIDENT.txt`.

## Next unit

* Santander scans whose amounts OCR damaged: d0c644cd5f5f7#1, d39807b9095f7#2, dfebde69177c4#1,
  d9fd8282f829e#1, da46a3c8e4979#1, dbbf41233fbf9#1/#2; d4394c6b6d780#1 has no geometry. Needs better
  reading, not engine rules.
* Santander holder where the page-1 name line itself is damaged: d6ad9634fb4ff#1, dc1e430221a20#1/#2,
  d8ce041307299#1, d6f43c4078e3a#1, d7ecc8297e894#1.
* Currency still held (6): d466de5b7cc20#1 and d5b19fa643804#1 (MONEDA line lost by OCR, correctly held);
  d997ce75a70a6#1 (BBVA, the currency phrase is OCR-garbled); d0b7a62995493#1 (Wells Fargo, no profile, only
  a symbol); df191ae7b7240#3 (Monex section in another currency) and d37df4b5e3403#1 (Intercam brokerage)
  not investigated deeply.
* No activity: the 4 BBVA card cycles print the payments component unreadably (held, deliberately);
  Capital One df9292c6e6c36#17/#18 are library-served by agreement and the engine proves them from card
  components only, which the generic zero-totals proof does not accept (a card-component quiet proof would
  serve them).
* Scotiabank (3): d889c7856ad55 not reconciled, dc3fbbaef34d0 no independent control, dec16784acb31 no
  opening and currency read as USD. The profile phrase is not found on these scans.
* kapital/mt-bank 3: not reached.

## Neil decisions

None needed for what landed. Two things he may want to rule on:
* Whether `holder_differs` for a legal-form punctuation difference ("S.A. DE C.V." against "SA DE CV")
  should count as a class in ready periods (the comparator is strict; the same 26 at wave9 and now).
* AGREEMENT_PREFERS_ENGINE moves agreed periods to the engine across families (product, saved statements
  engine/library 227/1099 at wave9, 416/927 now: BBVA 30 to 139 engine, Monex 33 to 59, Intercam 0 to 12,
  Kapital 3 to 10 as of 61c0f901) with no change in their readiness and 0 wrong values; it can be switched off in one line.
