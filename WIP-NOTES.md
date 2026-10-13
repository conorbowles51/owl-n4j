# r5-any-layout — WIP notes (real wave 5) — complete

Counts and opaque ids only. Private detail (surveys, dev tools, frozen code copies, scrub map) is under
`/mnt/owl-data/fin-real/tmp/r5/`; runs under `/mnt/owl-data/fin-real/bench/r5-*` and `/mnt/owl-data/fin-real/census-r5`.
Branch `fin/r5-any-layout`, based on fin/release-1 b484f376. Not pushed. Backend-only (no evidence-engine change,
no reading-revision bump; wave-4 readings reused everywhere).

History note: after the runs, the branch's own commits (after 712282cb) were rewritten once with `git filter-branch`
to replace literals taken from real statements (amounts, chart ticks, a description reference, an account fragment,
dates) in code comments, test literals and commit messages by synthetic values of the same shape. The rewritten code
is identical to the tested code apart from comments/docstrings (checked by comparing the modules' ASTs with
docstrings removed); the engine tests pass on the rewritten head. The whole-set run below ran on 73d5880f, which is
17b914ed before that rewrite.

## Landed (in order)

| Commit | What |
|---|---|
| 712282cb | Step 0.1: re-apply r4-any-layout (revert of the revert 2a9ba3ab) |
| 6cc4ea3f | Step 0.2/0.3: the holder never comes from movement text (heading cut at the first movement table; money/date lines never in an address block; the postal line must read as an address line); the printed account number beats the 18-digit interbank number that contains it (`account_basis` records which) |
| 6bc8d262 | Holder confirmed by a second printed fact: an addressee block reprinted in a postal-anchored fiscal block; the CFDI receipt recipient agreeing with a heading line |
| 38b91902 | Scan-noise glyph at an address edge; Scotiabank and Kapital institution profiles (data) |
| b8ba54fe | A section's repeated opening keeps its movement table (D6); routing row-level scope on shared pages; institution equality without generic banking words |
| 1bc26ee6 | Scan damage: decimal mark split by a space; date letter confusions (Q/O, L/I/| for 1, ~ for -, 0 for O in a month); period from a cut date + day count (yields to a labelled period of the same page run) |
| 88a533a9 | interim notes |
| 6bf44723 | Another table (other amount columns) after the movement table's own total is not this period's movements; letter-spaced heading words |
| 435b2a5a | A section on shared pages takes the account printed with its own opening (not a neighbour's chart legend); product-heading account read from one line of a cell |
| 978b07c2 | Credit-line statements: period over two lines, detached minus cell, credit number as account; guard: a company-name tail above an address block withholds its top line (a street) |
| 4ce822bd | Day column under a heading whose date word was lost (heading also gives column hints); column-rule '|' noise; ')' noise only in documents printing no parenthesised amount |
| 2e5dcffe | Chart axis ticks are not amounts (arithmetic run in one column, each once, contiguous); 'SALDO FINAL DE LA CUENTA' is a closing label |
| 47556f13 | Round 2: separators detached onto following groups; a dot glued inside a balance label |
| 17b914ed | Routing: an engine-served period on shared pages keeps no row and no page region overlapping another period's import region (fixes the 2 wrong admissions of the eebd4a3d whole-set run, below) |

## Step 0 (the r4 wrong admission) — fixed and proved

- The wrong period (opaque dcfc8ce1f2afc#1): holder now empty (held for the holder), account = the printed account
  number, not the interbank number.
- Private engine survey of all 567 truth documents (wave-4 readings, engine + profiles), proved periods matched to
  truth: holder differing from truth 1 -> 0, account differing 4 -> 0, currency differing 0, rows differing 0.
  Proved and matched: re-applied r4 860 -> final 882; holder equal 745 -> 772 (no proved holder lost).
- Interbank number where truth has the account number on proved periods: 84 -> 51; every remaining one is a layout
  whose interbank number does not contain the printed number, where truth also records the interbank number
  (Intercam/Kapital, 'contains' check); Santander/BBVA/Monex periods printing both now carry the printed account.

## Measured

### Whole-set real benchmark on final code (bench/r5-final; code 73d5880f = 17b914ed before the literal scrub)

567 truth documents (corpus copy `bench/r5-corpus`: the shared manifest filtered to the 567 documents with wave-4
readings; t-visual-v17 added Synchrony truth to the shared manifest during this unit), 1,237 distinct verified
periods, wave-4 readings (`--readings bench/wave4/engine-readings.json`), ~14.7 h, REAL_EXIT=0.

| | deployed (bench/wave4-a152) | with r4 (bench/wave4) | **final (bench/r5-final)** |
|---|---|---|---|
| Ready without any edit | 1,034 / 1,237 | 1,050 / 1,237 | **1,080 / 1,237 (87.3%)** |
| Recoverable ready | 1,034 / 1,233 | 1,050 / 1,233 | **1,080 / 1,233** |
| Wrongly admitted | 0 | 1 | **0** |
| Critical-field errors in saved rows | 0 | 15 | **0** (15,518 rows from 1,090 periods) |
| Batch items matched to no truth period | 37 (0 offered) | 35 (1 offered) | **33 (0 offered)** |
| Must-hold kept out | 4/4 | 4/4 | 4/4 |
| Exact copies held automatically | 148/151 | 148/151 | 148/151 |
| Previously ready periods lost | — | 0 | **0** vs wave4-a152 and vs wave4 |
| Engine-served / library-served ready | 46 / 988 | 62 / 988 | **92 / 988** |
| Engine-served ready with holder and account equal to truth | — | 62/62 | **92/92** |
| Currency-only holds | 10 (santander 7, bbva 2, monex 1) | 10 | **7** (santander 5, bbva 1, monex 1) |
| Valid-looking wrong values proposed (any period) | 73 | 71 | 80, **0 in ready periods** (all held: Andrews prefills 68, Kapital 7, Santander 2, Scotiabank 1, Intercam 1, Merrick 1) |
| Investigator actions per 100 statements (single / grouped) | 994 / 961 | 928 / 898 | **853 / 833** |

Per family (final vs deployed; engine / library; held reasons, overlapping):

| Family | Periods | Ready deployed | **Ready final** | Engine | Library | Held reasons |
|---|---|---|---|---|---|---|
| bbva-mexico | 371 | 333 | **355** | 22 | 333 | reading 11, balance 7, additional 4, no_activity 4, count 3, holder 2 |
| andrews-share | 270 | 200 | 200 | 0 | 200 | reading 46, balance 39, duplicate 8, no_activity 6, assignment 5 (other unit) |
| monex-mexico | 202 | 193 | **200** | 29 | 171 | balance 1, reading 1, currency 1 |
| capital-one-card | 119 | 117 | 117 | 0 | 117 | no_activity 2 |
| santander-mexico | 60 | 33 | **36** | 27 | 9 | holder 14, balance 6, reading 5, currency 5, account 2 |
| credit-one-card | 53 | 51 | 51 | 0 | 51 | reading 2 |
| citi-card | 49 | 49 | 49 | 0 | 49 | — |
| intercam-mexico | 42 | 30 | **35** | 5 | 30 | balance 7, reading 4, no_activity 2 |
| merrick-card | 42 | 16 | 16 | 0 | 16 | dates 15, balance 12, holder 11 (other unit) |
| kapital-mexico | 20 | 12 | **16** | 4 | 12 | balance 4, reading 3, no_activity 1 |
| scotiabank-mexico | 7 | 0 | **5** | 5 | 0 | balance 2, institution 2, reading 2 |
| first-caribbean / intercam-brokerage | 1 / 1 | 0 / 0 | 0 / 0 | 0 | 0 | balance / no movements |
| **total** | **1,237** | **1,034** | **1,080** | **92** | **988** | |

Gained 46 vs deployed (30 vs wave4 with r4), lost 0. The step-0 file: its former wrong period (a copy) is held for
the holder; its two other periods now prove and are held only for a currency line the scan lost (one confirmation).

Layout-memory confirmations that would clear the remaining identity-only holds: 22 held periods with a printed
account, cleared by **6** one-per-account confirmations (Santander holder 10, Merrick holder 7, Santander currency 4,
Monex currency 1); 2 more print no account.

Per-statement comparison (bench/r5-final/compare, private): 567 statements, 1,441 periods + unmatched items; without
any disagreement **1,225** (wave 4: 1,150 of 1,445). holder_differs 26, all BBVA and all differing only in printed
punctuation/spacing of the legal form (24 in ready periods: the truth convention r4 recorded); no money, date,
currency or account class in any ready period.

Earlier whole-set run on eebd4a3d (bench/r5-final-eebd4a3d): 1,080 ready but **2 wrongly admitted** (8 missing
rows): two held Intercam peso periods shown as imported by the batch view because the engine-served dollar period's
scope kept two footer rows overlapping the peso period's import region (nothing saved for them). Fixed in 17b914ed
(73d5880f); proved by a harness replay of the 10 affected files and by the final whole-set run above.

### Generic-only figure (engine + profiles, every family reader skipped; bench/r5-generic, code eebd4a3d)

**717 / 1,237** ready (r3's last harness figure: 620 / 1,092 on older truth). Engine-served ready periods with holder
and account equal to truth: 717/717. Per family: bbva 354/371, monex 166/202, capital-one 99/119, intercam 37/42,
santander 27/60, citi 15/49, kapital 14/20, scotiabank 5/7, andrews 0/270, credit-one 0/53, merrick 0/42 (no
period detected without their readers). The harness reports 5 wrongly admitted in this mode: all five are the
Santander investment-product zero sections, each equal to its truth period in account, dates, currency, both
balances (0/0), rows (0) and holder; the harness's greedy pairing gave that truth period to a held item of the same
file first, so the correct item paired with nothing ("unmatched"). A scoring artefact of this measurement mode; not
changed here (benchmark rule).

Engine-alone survey (private, money + currency equal to truth, incl. copies, 1,386 truth periods): fin/release-1
754 -> r4 re-applied 838 -> final 855 (bbva 361, monex 170, capital-one 195, santander 43, intercam 37, citi 30,
kapital 14, scotiabank 5).

### Census (all 6 cases, cached readings, census-r5, code eebd4a3d)

**1,165** periods ready with zero edits (census-wave4 on 8f9258c8: 1,118); engine-read ('generic') 41 -> 88.
Held only for currency: generic 196 (186 on the redacted 345-page production) + no_statement_found 44 = 240
(wave 4: 241); santander 24, bbva 4. Engine-proved periods held only for the holder ('generic', M&T and others): 62,
in 5 printed accounts (5 confirmations). Nothing on documents without truth is counted as verified.

## Tests actually run

- Engine module `tests.test_financial_statement_engine`: 117 OK on the final head (75 before this unit's tests:
  42 new tests across 15 classes; each new reading test checked to fail on the code before its rule, except the
  stated guard tests).
- Engine/routing-adjacent modules (layout memory, import batches, OCR word tables, engine): 228 OK on 73d5880f.
- Full financial suite on 73d5880f (worktree): Ran 6,055, failures=2 (the known `unassigned_statement` pair),
  errors 0, skipped 20. (Also on cebec45e: 6,050, same 2; on eebd4a3d from a frozen copy: 6,052, same 2 + the known
  frozen-copy artefact in test_financial_statement_details, 66 OK in the worktree.)
- Synthetic benchmark: 105/125, recoverable 105/108, 0 wrong, 0 critical, holds 10/10, BENCH_EXIT=0 on cebec45e,
  eebd4a3d and 73d5880f (bench-runs/r5-any-layout-{cebec45e,eebd4a3d,73d5880f}).
- Frontend not touched (no tsc/vitest run).

## Open / next unit

- BBVA vector-outline cash-management statements (4 long ones + several short, 'reading'/'additional'): the OCR
  misreads digits (e.g. a 5 read as 9) on pages that render crisply at 400 dpi (checked visually on one cell). Needs an
  evidence-engine change (render/OCR dpi for `vector_text` pages or a money-cell re-read there; see
  `evidence-engine/app/pipeline/pdf_extraction.py` `_render_dpi`), a fresh read of a mini corpus and a reading-revision
  bump. Not backend work.
- BBVA credit line with movements (3 truth periods): truth books interest/VAT printed only as summary amounts as rows
  at the cut date; the engine does not invent rows. A library reader for that layout (or a truth convention decision).
- Monex df191ae7b7240 (#1, #3): six amount columns with explicit zeros -> too many interpretations; Monex library
  serves the rest.
- Intercam/Kapital peso sections whose movement lines lost their day (ded55a9f9e81b#1) or whose library and engine
  scopes differ on furniture rows (the peso period is not replaced when the library period claims rows the engine
  does not read).
- Santander scans with heavy OCR damage (d8af2d5c29493, da46a3c8e4979, d5b19fa643804, d4394c6b6d780 no geometry,
  dbbf41233fbf9 no geometry, d8b0192c926db): left held.
- First Caribbean (one document): whole-euro amounts without cents are refused for a two-decimal currency (by design).
- Harness pairing (benchmark only, not changed here): pairing is greedy in file order and the last remaining truth
  period goes to whichever item asks, regardless of account; in the generic-only run it paired 5 correctly read
  Santander zero sections to nothing ("unmatched") — see Measured. A global (max-score) pairing would remove this
  artefact; a decision for whoever owns the harness.

## Decisions taken (each reversible in one place)

1. Holder search stops at the statement's first movement table (heading or movement line). Reverse: `_identity_rows`.
2. Postal line forms: labelled code (one scan substitution in C.P.), leading code + place, code after a US state, code
   closing a 'place, place' line. Reverse: `_postal`.
3. Printed account number over the interbank number containing it. Reverse: `_printed_over_interbank`.
4. Addressee confirmation by a reprinted address block or the CFDI recipient. Reverse: `_reprinted_block` /
   `_receipt_holder`.
5. Lone noise glyph at the address edge ignored. Reverse: `_lead_noise`.
6. Scotiabank/Kapital institution profiles (data). Reverse: remove the two profile entries.
7. Routing row-level scope: furniture rows may be shared for the scope check, but a served period's own scope drops
   them and must not overlap another period's import region. Reverse: `_rows_apart`, `_own_scope`, `_covers`.
8. Institution equality ignoring generic banking words and accepting a shared first distinctive word (former names).
   Reverse: the `institution` branch of `_same_identity`.
9. Cut date + day count period (dropped if contradicted by a labelled period of the page run). Reverse:
   `_derived_period`.
10. Other table after the movement table's total. Reverse: `other_table` in `_reading`.
11. Day column inferred from a dateless heading. Reverse: `_lost_day_heading`.
12. ')' after an amount is noise only in documents with no parenthesised amount. Reverse: `_NO_PARENS`.
13. Chart scale marking. Reverse: `_mark_chart_scale`.

## Decisions needed from Neil

None to continue.
