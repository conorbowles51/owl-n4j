# r2-any-layout — WIP notes (real wave 2)

Counts and opaque ids only. Private detail (per-statement comparisons, readings, visual records, dev tools) is
under `/mnt/owl-data/fin-real/` (listed at the end). Branch `fin/r2-any-layout`, based on fin/release-1
8338cebe. Not pushed.

## Landed

| Commit | What |
|---|---|
| a8af3a1e | General statement engine (`statement_engine.py`), one vocabulary table (`statement_engine_vocabulary.py`), routing (`statement_engine_routing.py`, engine primary, family readers as fallback library), hooks in statement_import / review checks / currency, 26 engine tests, knowledge file |
| 6c7c8336 | Sections and per-section currency attribution, row-level `section_sources` for sections sharing a page, proposals re-read the whole document (cached by source revision + content) |
| 7631b6c0 | Holder from the statement's first pages, addressee block on either side. **Blind run frozen here.** |
| 8f4da89e | Library profiles (data) with Capital One and BBVA expressed as profiles; OCR accent tolerance in labels (F1); two period formats |
| 4fe4a6f4 | Account only from heading pages (blind-run finding); routing never takes a reconciling library period; identity inherited / conflict keeps library; route-table generator |
| aeb02522 | Whole printed account numbers (digit groups across cells), addressee spacing, no guessed prefill for held periods |
| cab8e6e4 | Holder labels with their colon, NOT_A_NAME list, single-statement label fallback (synthetic regression fix), repeated-summary merge |
| 2972d6eb | Engine modules exported from the package (package-surface test); knowledge file final coverage |
| 8f8a7859 | Three library tests pinned to library mode (they simulate "no family reader" or test a reader's own refusal) |
| 4044a1a2 | Source-signature refactor (a per-document catalog cache was tried and reverted: it hid test patches) |
| c6679b95 | **Engine on by default** (`DEFAULT_ENABLED = True`), default test |
| (this commit) | WIP-NOTES.md |


## The scale number (leave-families-out, measured once)

Decided before building: development families bbva-mexico, monex-mexico, capital-one-card (+ synthetic);
held-out santander-mexico, intercam-mexico, kapital-mexico, citi-card. andrews-share was in neither list and was
never opened during development; it is reported with the held-out side. Engine-only mode
(`LOUPE_FINANCIAL_GENERIC_ONLY=1`, every family reader skipped), real harness on the verified truth, engine code
frozen at **7631b6c0**, cached wave-1 engine readings (`bench/r2-blind-generic`, `bench/r2-dev-generic`).

| Side | Family | Verified periods | Ready w/o edits | Wrong admissions |
|---|---|---|---|---|
| development | bbva-mexico | 344 | 329 (95.6%) | 0 |
| development | monex-mexico | 171 | 46 (26.9%) | 0 |
| development | capital-one-card | 119 | 0 (institution never printed as a legal name) | 0 |
| **development total** | | **634** | **375 (59.1%)** | **0** |
| held-out | santander-mexico | 41 | 0 | 0 |
| held-out | intercam-mexico | 30 | 0 | 0 |
| held-out | kapital-mexico | 14 | 0 | 0 |
| held-out | citi-card | 46 distinct (92 with copies) | 0 | 0 |
| not used in development | andrews-share | 270 | 0 | 0 |
| **held-out total** | | **401** | **0 (0.0%)** | **0** |

Why each held-out period was held (engine terms, scored periods incl. copies):
- santander-mexico 41: engine PROVED the money reading of 24 (22 equal to truth; 2 had a counterparty CLABE as
  account, fixed in 4fe4a6f4) but held for holder 19 / holder+institution 2 / account+holder+institution 2 /
  account+institution 1; currency not read 8; not reconciled 7; printed total differs 1; date outside period 1.
- citi-card 92: engine PROVED 26 (20 equal to truth; 6 are 3 cycles x 2 copies that the harness paired with the
  wrong cycle of the same file - checked: each equals its own verified cycle exactly) but held for
  holder/institution; currency not read 56 (the bare '$' rule did not fire on those cycles; cause not investigated); not reconciled 4; date order 4.
- intercam-mexico 30: not reconciled 13, no independent control 9, currency not read 5, printed total differs 2,
  not detected 1.
- kapital-mexico 14: printed total differs 5, not detected 4, no independent control 3, not reconciled 2.
- andrews-share 270: 257 produced no engine period at all (scanned share statements; the engine's period and
  control vocabulary does not match their headings); currency not read 10; no opening 3.
The hold-out ended after this figure (recorded 2026-10-06 ~06:40). Generalisation of the money reading is
much better than the ready figure suggests: on held-out families the engine proved 50 periods, every one equal
to verified truth once the account fix landed; readiness then failed on identity facts the engine cannot read
generically (holder, institution, a bare '$' currency), which are grouped decisions.

After the hold-out (current code, engine alone, offline against ALL verified truth, 514 documents): **731 periods
proved and equal to verified truth, 0 proved periods that differ** (bbva 333, capital-one 197 + 18 equal to
ocr_reconciled truth, monex 141, santander 32, citi 28 + 2, ...). Accounts agree for every proved period that has
one; holders agree except 3 Monex periods where the truth reader took the street line (known truth defect).

## Normal mode (engine primary, library fallback), full real benchmark

Real harness, frozen 485-document snapshot (1,035 distinct verified periods), cached wave-1 engine readings,
engine code cab8e6e4 (later commits are tests/exports/refactor only), `bench/r2-engine-on`, exit 0.
"Before" = wave 1 (`bench/wave1`, the same code without the engine, same truth).

| | before (wave 1) | **after (engine primary, library fallback)** |
|---|---|---|
| Ready without any edit | 800 / 1,035 (77.3%) | **821 / 1,035 (79.3%)** |
| Recoverable ready | 797 / 1,028 | **818 / 1,028** |
| Wrong admissions | 0 | **0** |
| Critical-field errors in saved rows | 0 (10,622 rows) | **0 (11,514 rows from 835 periods)** |
| Must-hold kept out | 4 / 4 | 4 / 4 |
| Exact copies held automatically | 145 / 145 | 145 / 145 |
| Valid-looking wrong values proposed (held periods) | 86 | 80 |
| Previously ready periods lost | — | **0** |
| Investigator actions (single / grouped), 485 statements | 4,963 / 4,772 (1,023 / 984 per 100) | **3,057 / 2,954 (630 / 609 per 100)** |
| Preparation / import wall time | 4,753 s / 20,182 s | 4,439 s / 22,694 s |

Per family (engine-served / library-served / held with reasons / wrong):

| Family | Verified | Ready before | Ready after | Engine-served | Library-served | Held (reasons) | Wrong |
|---|---|---|---|---|---|---|---|
| bbva-mexico | 344 | 333 | 333 | 0 | 333 | 11 (reading 10, balance 3, count 1) | 0 |
| monex-mexico | 171 | 171 | 171 | 0 | 171 | 0 | 0 |
| capital-one-card | 119 | 116 | 116 | 0 | 116 | 3 (no_activity 2, unexplained 1) | 0 |
| citi-card | 46 | 46 | 46 | 0 | 46 | 0 | 0 |
| intercam-mexico | 30 | 22 | 22 | 0 | 22 | 8 (no_activity 8) | 0 |
| kapital-mexico | 14 | 4 | 4 | 0 | 4 | 10 (not_detected 5, balance 3, no_activity 2, reading 1, institution 1) | 0 |
| santander-mexico | 41 | 9 | **30** | **21** | 9 | 11 (institution 6, balance 6, reading 5, account 3, not_detected 1) | 0 |
| andrews-share | 270 | 99 | 99 | 0 | 99 | 171 (balance 103, reading 98, not_detected 41, holder 34, duplicate 8, no_activity 7, assignment 5) | 0 |
| **total** | **1,035** | **800** | **821** | **21** | **800** | 214 | **0** |

Reasons overlap. The 21 gained periods are Santander statements no family reader claims (inventory mislabels
them); every one of the 21 equals verified truth (offline check) and 8 of them were also read from the page
images (visual sample). Engine-held periods listed on those documents: 3 (identity facts).


## Routing (current code, all 485 truth documents, offline)

- Engine-served: 24 periods (Santander documents no family reader claims), engine-held listed: 4.
- Library-served: every other period. Cross-checked where both proved the same pages: 94 (BBVA 59, Citi 30,
  Monex 5), **0 disagreements**, 0 replacements (no library period failed its closing check while the engine
  proved it).
- Extra reading time: engine alone 143 s over 514 documents (median 0.13 s, p95 0.44 s, max 7.9 s); catalog
  with engine + library cross-check ~0.45 s per document on average (235 s for 485 documents).
- The cross-check only runs when the engine's page set equals the library group's; many BBVA/Capital One
  periods are therefore not cross-checked (conservative: nothing is served or held because of it).

## Previously unread documents

- Census population no reader read (census family no_statement_found / unknown / no_period, 116 distinct
  originals): the engine now proves **33 periods on 33 documents** (24 also have verified text-layer truth and
  equal it; 9 had no truth).
- Vector-text documents (125, 1,013 pages): all already read through image recognition by the evidence engine
  (no routing change needed). Engine proves 26 periods on 26 of them (10 on documents no reader read before);
  141 held (not reconciled 56, no opening 31, unplaced money line 22, ...): OCR damage, next unit.
- **Visual verification: 20 periods** rendered with PyMuPDF and read from the page images (opening, closing,
  printed counts/totals and every movement: 109 movement lines): **20/20 equal to the engine to the cent**
  (9 without any prior truth, 11 also with text-layer truth). Two defects found and fixed on the way: a
  fiscal-address heading taken as holder; a repeated summary listed as a second held period. The 9 new
  periods are written as harness truth (private) for the integration session to merge.
- On the 29 documents t-visual-v07 verified meanwhile (42 periods, independent truth): engine off 0/42 ready,
  engine on 0/42 ready, 0 wrong either way; after the prefill fix the valid-looking wrong values proposed
  are 2 (as with the engine off).

## Synthetic

- Engine off: unchanged code paths (the engine does not run) = last recorded 105/125.
- Engine on (`bench-runs/r2-any-layout-engine-on-2`, backend rerun on the run's own engine readings):
  **105/125 ready, 105/108 recoverable, 0 wrong, 0 critical, holds 10/10, copies 1/1, exit 0; no period lost
  or gained.** The first engine-on run (84/125) exposed the holder-label defect fixed in cab8e6e4.

## Profile format (library, data)

`statement_engine_profiles.py`: `name`, `match` {any, all phrases}, `institution`, `currency` (for a bare
symbol), `convention` (asset_balance | liability_owed), `date_order` (dmy | mdy), `labels` {opening, closing,
subtotal, credit_total, debit_total, credit_component, debit_component, column_total}, `columns` {date,
description, credit, debit, balance, amount}. Validated on load. Capital One and BBVA Mexico are expressed as
profiles (their code readers stay). Routing uses a matching profile only when it keeps every period the plain
engine proves with the identical money reading; proposals re-read with the same profile.

## Knowledge file

`docs/financial-workflows/statement-engine-knowledge.md`: **47 rules**; engine covers **41**, partially **2**,
library-only **4**. Each rule names the families that need it.

## Tests actually run

- `tests.test_financial_statement_engine`: 33 tests (26 reading/routing + 5 profile + 2 routing safeguards) OK.
- 20 targeted statement-import modules + engine: 352 OK (engine off). With the engine on: the same modules show 3
  expected changes (2 BBVA tests that simulate "no family reader" to exercise legacy recovery, 1 Credit One
  identity test) because the engine now reads those pages.
- Full financial suite with the engine ON (environment): 5,840 tests, failures: the package-surface test (fixed
  in 2972d6eb), the 2 known `unassigned_statement` failures, and the 3 tests above. Final, with the engine on by default (c6679b95): **Ran 5,841, failures=2** (the two known
  `unassigned_statement` failures), skipped 20 - the recorded baseline (5,807, failures=2) plus 34 new engine tests.
- Synthetic with the engine on: see above (105/125, exit 0). Frontend untouched (no tsc/vitest run).

## Decisions taken (each reversible in one place)

1. **Engine ON by default** (engine primary, family readers as fallback library): every mode measured 0 wrong
   admissions, the 20-period visual sample agreed to the cent, no period ready with the library alone was lost
   (real 0 lost / 21 gained; synthetic 0 / 0). Reverse: `DEFAULT_ENABLED = False` in
   `statement_engine_routing.py` or `LOUPE_FINANCIAL_GENERIC_READER=0`. Deploy note: the engine is backend-only
   (no evidence-engine change, no migration); it changes which periods are listed for documents no family reader
   claims, and adds review rows that name why an engine period is held.
2. Hold-out breach: one Santander document (opaque id d8a9874bf0d81) had its table sources dumped once at the
   very start, before the guard existed (the inventory guessed it as BBVA). Nothing was tuned on it; no
   Santander-specific rule exists in the engine. Recorded so the figure is read with that caveat.
3. Library periods that reconcile are never replaced by the engine; the engine serves only pages no library
   reader claims, or a library period whose own reading fails its closing check (with the library's identity
   facts, never against them). Reverse: `closing_reconciles` guard in `statement_engine_routing.py`.
4. A bare `$` is USD only with a US postal address and no peso wording (C2). Reverse: `_us_dollars`.
5. Held engine periods prefill a column reading only when it reconciles the printed balances.
6. Card summary components are a printed control only between the previous and the new balance (D7).

## Not done / next unit (r3-any-layout)

1. Identity facts for unseen banks are the main reason engine-proved periods are held (holder, institution, '$'
   currency): build **layout memory** - when a person confirms holder/institution/currency once for a layout
   fingerprint + account, store it as a profile entry (data) so every later period of that layout is ready.
   This is also the batch workflow: group held engine periods by (layout fingerprint, account, missing fact) and
   confirm once.
2. Convert more family readers to profiles (Monex, Santander, Kapital/Intercam headings and labels).
3. Andrews (scanned share statements): engine produces no period; its period headings and "Previous/New
   balance" share layout need either profile labels or the existing reader stays primary.
4. OCR damage on vector-text Santander documents (not reconciled / no opening on 141 periods).
5. The cross-check covers only periods whose engine page set equals the library group's; widen to row-level
   section scopes so every library period is cross-checked.
6. Merge the private visual truth (`fin-real/truth-r2-visual/manifest.json`, 9 periods) into the shared truth.

## Decisions needed from Neil

None needed to continue. Two to note: (1) deploying this switches the engine on for live batches (listed held
periods appear on documents that showed "no statement found"; reverse with the environment switch above);
(2) the blind scale number is 0/401 ready: the engine reads unseen banks' money correctly (50 held-out periods
proved, all equal to truth after one fix) but cannot name holder/institution/bare-$ currency for them, so they
wait for a grouped confirmation. Layout memory (next unit) is the recommended fix.

## Private artefacts (`/mnt/owl-data/fin-real/`, mode 700)

- `bench/r2-blind-generic` (blind figure), `bench/r2-dev-generic`, `bench/r2-engine-on` (full normal mode),
  `bench/r2-newtruth-0|1|1b`, `bench/r2-mini-generic-*`; aborted runs `bench/r2-engine-on-aborted*`.
- `compare/r2-any-layout/{blind,dev,engine-on}`: per-statement comparisons written by the harness.
- `truth-r2-visual/manifest.json`: 9 visually verified periods (harness format).
- `tmp/r2/`: dev tools (dev.py with the hold-out guard, eng.py, why.py, render.py, engval.py,
  routing_census.py, beforeafter.py), `visual/` (rendered crops + `visual-truth.json`, 20 periods),
  `PROGRESS.md`, `holdout-breaches.txt`.

