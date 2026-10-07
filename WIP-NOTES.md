# r3-any-layout — WIP notes (real wave 3)

Counts and opaque ids only. Private detail (per-statement comparisons, readings, visual records, dev tools)
is under `/mnt/owl-data/fin-real/` (listed at the end). Branch `fin/r3-any-layout`, based on fin/release-1
d36fd235. Not pushed. Final code: b4cbb779 (+ this notes commit).

Commit ids on this branch were rewritten once before this notes commit to remove values copied from real
pages (one account number in a comment, one account prefix in a comment, identifiers in one test fixture, a
balance in one commit message); code is unchanged. Benchmarks ran on frozen copies of the pre-rewrite
commits; their code equals the commits named here (old -> new mapping in `tmp/r3/hash-map.txt`).

## Landed

| Commit | What |
|---|---|
| 80f53c5f | **Layout memory** (item 1): an identity fact a person confirms once is stored as data, keyed by (field, printed account, balance convention, the field's printed identity evidence); grouped decisions per batch with the machine's proposal prefilled; withdraw re-reads and holds again; API + `BatchLayoutMemory` panel |
| acf22039 | Engine identity (item 2): holder names with letter-digit tokens; bank legal-name tiers; every occurrence of a currency label |
| 6b681738 | Sideways pages (evidence engine + backend + engine), institution-only profiles (Monex, Santander, Intercam, Citi), generic-only mode applies profiles |
| 33d0ea0b | Kapital/Intercam quiet sections: the empty table's own zero Total line is a printed control |
| 54f6258c | Engine/library cross-check at row-level scope (item 5) |
| ed058f2e | Santander profile `account_heading` (account printed only after the product name) |
| e2bc280f | Kapital reader: truncated product heading; currency and scope per product |
| 231373c7 | Engine holder: ZIP+4 postcodes; the issuer is never the holder; no one-word bank names |
| e4b5650c | Monex profile `statement_account` (one contract for all currency sections) |
| 8f7f7313 | Engine holder: addressee row merged with the right column; one blank line before the postcode |
| 39bd72ee | Layout memory API: `GET /layout-memory/confirmations` (the first path was shadowed by `GET /{evidence_file_id}`) |
| 0a593f37 | **Correction of 6b681738**: upright table frame only when the recognised words stand on end |
| 5e628f57 | Import overlap guard measures section regions upright on sideways pages (found by the real benchmark) |
| 8fae625f | Engine proof: a running-balance column that does not chain cannot prove by printed totals |
| b4cbb779 | Engine: the second date under a posting heading is the posting date (found by the generic-only benchmark) |
| abfccc6d, 62777312, 78e6e09f | Knowledge file (F4, profiles, cross-check, open defects, late rules) |

## Real benchmark (normal routing, engine primary + library fallback)

Corpus: the 525 documents of bench/wave2 with the shared truth as of 02:57 today (the truth unit had updated
3 Citi documents: +3 verified periods; frozen copy `tmp/r3/corpus525`). Readings: bench/wave2 readings for
516 documents; fresh reads (evidence engine 0a593f37) for the 9 documents with sideways pages (the only
documents whose reading the engine change alters: every other page keeps the earlier grouping exactly).
Run B = full harness on frozen code 62777312 (`bench/r3-any-layout`, ~13.7 h on a loaded host). The final
code differs from 62777312 only on those 9 documents in normal routing (checked: of 45 documents whose engine
balances change under 8fae625f, one is engine-served in normal routing and it is one of the 9; the posting-
date rule only applies under posting headings, which only the card families print, and those are library-
served), so the final figure = run B with the 9 documents replaced by a final-code run of them
(`bench/r3-any-layout-sideways9-final`; no truth duplicate links them to other documents), metrics recomputed
with the harness's own `metrics()` (`tmp/r3/results-final-merged.json`).

| | wave 2 (bench/wave2) | **r3 final** |
|---|---|---|
| Ready without any edit | 821 / 1,089 (75.4%) | **860 / 1,092 (78.8%)**; on the 1,089 periods present in both: 857 |
| Recoverable ready | 818 / 1,082 | **860 / 1,088** |
| Wrong admissions | 0 | **0** (run B on 62777312: 1, the sideways overlap defect fixed in 5e628f57; final-code run of those documents: 0) |
| Critical-field errors in saved rows | 0 | **0** (run B: 1, same defect) |
| Must-hold kept out | 4 / 4 | 4 / 4 |
| Exact copies held automatically | 145 / 145 | 148 / 148, 0 offered |
| Previously ready periods lost | — | **0** |
| Valid-looking wrong values proposed (held periods) | 89 | 89 (date 55, amount 33, currency 1), 0 in ready periods |
| Investigator actions per 100 statements (single / grouped) | 958 / 928 | **945 / 922** |

Per family (engine-served / library-served / held with reasons, overlapping):

| Family | Periods | Ready before | Ready after | Engine | Library | Held (reasons) | Lost | Gained |
|---|---|---|---|---|---|---|---|---|
| andrews-share | 270 | 99 | 99 | 0 | 99 | 171 (balance 103, reading 99, not_detected 41, holder 34, duplicate 8, no_activity 7) | 0 | 0 |
| bbva-mexico | 357 | 333 | 333 | 0 | 333 | 24 (reading 21, balance 7, count 4, holder 3, additional 3, currency 1) | 0 | 0 |
| capital-one-card | 119 | 116 | 117 | 0 | 117 | 2 (no_activity 2) | 0 | 1 (copy pairing) |
| citi-card | 49 | 46 | 49 | 0 | 49 | 0 | 0 | 3 (periods the truth unit added) |
| intercam-mexico | 38 | 22 | **30** | 0 | 30 | 8 (balance 7, reading 4, no_activity 4, holder 1) | 0 | 8 |
| kapital-mexico | 18 | 4 | **12** | 0 | 12 | 6 (balance 5, reading 4, institution 1, no_activity 1, not_detected 1) | 0 | 8 |
| monex-mexico | 187 | 171 | **187** | 16 | 171 | 0 | 0 | 16 |
| santander-mexico | 50 | 30 | **33** | 24 | 9 | 17 (balance 10, reading 9, currency 5, holder 3, account 1, not_detected 1) | 0 | 3 |
| scotiabank-mexico | 2 | 0 | 0 | 0 | 0 | 2 (currency 2) | 0 | 0 |
| first-caribbean / intercam-brokerage | 1 / 1 | 0 / 0 | 0 / 0 | 0 | 0 | 1 / 1 | 0 | 0 |
| **total** | **1,092** | **821** | **860** | **40** | **820** | 232 | **0** | **39** (35 by code) |

Gains by cause: the 16 Monex periods on 8 sideways documents (wave 2: "not detected"); 10 Kapital/Intercam
quiet USD sections (zero Total line) + 4 Kapital USD sections never detected + 2 Kapital peso sections whose
balances were polluted by the undetected USD section; 3 Santander zero-activity periods (account heading).

Engine/library cross-check (offline, all 525 documents): cross-checked library periods 94 -> 485 (BBVA 329,
Monex 117, Citi 30, Capital One 9), 0 disagreements.

## Generic-only figure (engine + data profiles, every family reader skipped; reported every wave)

Run C (`bench/r3-any-layout-generic`, frozen 62777312) for every family except Monex and the cards, which
were re-run on the final code (`-generic-monex` on 8fae625f, `-generic-cards` on b4cbb779; all 45 documents
whose engine balances changed are Monex, so run C equals the final code for the other families).
**620 / 1,092 ready (56.8%), 0 wrong admissions on the final code.**

| Family | Periods | Ready | Main holds |
|---|---|---|---|
| bbva-mexico | 357 | 329 | reading 26, balance 5, count 3, holder 3 |
| monex-mexico | 187 | 153 | reading 20, balance 20, holder 10, institution 9, account 8 |
| capital-one-card | 119 | 99 | holder 13, reading 10, balance 10, duplicate 7 |
| santander-mexico | 50 | 24 | reading 13, balance 13, currency 13, holder 3 |
| citi-card | 49 | 15 | currency 15, not_detected 15 |
| intercam-mexico | 38 | 0 | reading 36, balance 36, institution 32 |
| kapital-mexico | 18 | 0 | reading 13, institution 13, balance 13 |
| andrews-share | 270 | 0 | not_detected 257 (engine reads no share statement) |
| scotiabank / first-caribbean / intercam-brokerage | 2 / 1 / 1 | 0 | currency / balance / reading |

r2 recorded 375/634 (development) and 0/401 (held-out) on wave-1 truth. Run C on 62777312 had 95 wrong
admissions: 94 Capital One/Citi periods with posting dates missing (fixed in b4cbb779; card rerun 0 wrong,
posting dates equal to truth on 1,559 + 114 rows) and the sideways overlap defect (fixed in 5e628f57).
Engine-only mode recognised 105 of 145 card copies automatically (the 40 others held, none offered); normal
routing 148/148.

## Layout memory (item 1) measures

- Start of unit (plain engine, verified truth): 295 money-proved periods lacked an identity fact; 37
  confirmations would complete them (formerly held-out families: 36 periods, 9 confirmations).
- After the identity work (generic-only routing, final code): development families 687 money-proved and
  equal to truth, 603 already identity-complete, 84 completed by 43 holder confirmations; formerly held-out
  families 62 proved, **54 identity-complete without any confirmation (was 19)**, 4 more by 2 currency
  confirmations, 4 print no account (memory never applies).
- Normal routing, verified set: 12 identity decisions answerable by memory (10 confirmations), so actions per
  100 barely move there (grouped by actual value 923, with memory 924; harness family-level model 922).
  Memory's value is persistence: a later batch of the same account and layout needs no identity action.

## Newly ready periods on documents no reader read before (visually verified)

18 periods on 9 documents (rendered with PyMuPDF, read from page images, private `tmp/r3/visual.md`): the 10
peso/euro periods of 5 sideways Monex statements with verified truth, and 8 periods on 4 never-read sideways
Monex statements with no truth yet. **18 / 18 equal to the engine to the cent** (opening, closing, every
movement, printed credit/debit totals). The 8 no-truth periods are candidates for the truth unit.
Never-read population (199 documents, current readings): engine-proved periods 33 -> 33, identity-complete 21
-> 23; of 90 never-read documents with a recorded OCR turn, 17 have sideways pages (9 in the truth set, 8
read fresh: 4 proved as above, 4 held "no movements or controls"). Full census not re-run this wave.

## Tests actually run (final code b4cbb779 unless noted)

- Backend financial suite: **Ran 5,896, failures=2** (the known `unassigned_statement` pair), skipped 20.
- New/extended: layout memory 11, engine 47, ocr word tables 10, kapital 10, mexico no-activity 21; each new
  regression test checked to fail on the commit before its fix.
- Evidence engine: **694 passed, 14 skipped** (0a593f37; later commits are backend-only).
- Frontend: `tsc -b` 0; vitest unit **297 files, 2,060 tests passed**; eslint 0 on the changed files.
- Synthetic: **105 / 125**, recoverable 105/108, 0 wrong, 0 critical, holds 10/10, copies 1/1 (final code,
  `bench-runs/r3-any-layout-final3`; also 105/125 on 62777312 and 8fae625f).

## Decisions taken (each reversible in one place)

1. Layout memory is per case, keyed by printed account + the field's printed evidence + convention; the
   layout key is recorded and used for grouping, not for the match (heading OCR splits one account into many
   keys). Reverse: add `layout_key` to `layout_memory.memory_key`.
2. Confirmations live in `EvidenceFile.metadata_['financial_layout_memory']` (no migration). Reverse: a
   table + migration.
3. A remembered holder/bank stays outside the reading revision (saved corrections never invalidated); a
   remembered currency is the currency the amounts are read in. Reverse: in `statement_import`.
4. Institution-only profiles (Monex, Santander, Intercam, Citi) and the Santander `account_heading` / Monex
   `statement_account` options are data in `statement_engine_profiles.py`. Reverse: delete the entry/flag.
5. Sideways pages: upright table frame only for 90/270-degree readings whose words stand on end. Reverse:
   remove the branch in `pdf_extraction._read_ocr_page` (pages return to the displayed grouping).
6. Kapital/Intercam: the empty table's zero Total line (0, 0, closing balance) is a printed control. Reverse:
   `zero_total` in `kapital_no_activity_evidence`.
7. Row-level cross-check pairs only the same period, currency, printed account and opening balance.
8. A non-chaining running-balance column cannot prove by totals; posting headings make the second date the
   posting date.

## Open / for the next unit (r4-any-layout)

- Santander (17 held): a section on shared pages takes the main account's heading (zero product gets the main
  account, detail gets none); drawn-table rows fusing the last movement with the TOTAL line (3 documents);
  mixed decimal separators on scanned pages (10 periods).
- BBVA 24 held (reading 21); Intercam/Kapital remaining balance/reading holds; amounts read with a trailing
  ')' or '?' glyph (5 quiet sections held for a person).
- Vector-outline documents (item 4, not addressed): 158 engine periods, 24 proved (0 differ), 134 held
  (not reconciled 52, no opening 30, unplaced money line 22, no movements/controls 15, date unresolved 8).
- Never-read: a 345-page credit-union production yields 287 engine periods, none provable as read (needs
  truth first); 4 never-read sideways documents held; re-run the census on the final code.
- Generic-only: Intercam/Kapital 0 (institution and readings), Andrews 0 (engine reads no share statement),
  engine-only copy recognition 105/145.
- Truth defects for the truth unit (not edited): 7 Monex periods on 4 documents carry the holder
  "Institución de Banca Multiple," (page image shows the company the engine reads).

## Decisions needed from Neil

None to continue. For deploy: the evidence engine and backend changes go together (the upright table frame
needs both; documents with sideways pages must be re-read to benefit; no other reading changes). The batch
view gains a "Confirm details once for matching statements" panel.

## Private artefacts (`/mnt/owl-data/fin-real/`, mode 700)

- `bench/r3-any-layout` (run B), `bench/r3-any-layout-sideways9-final`, `bench/r3-any-layout-generic`
  (run C), `-generic-monex`, `-generic-cards`, `bench/r3-any-layout-sideways9` (pre-chain-fix), stopped run
  `bench/r3-a-oldreadings` (partial, ignore).
- `compare/r3-any-layout/{normal,generic,generic-monex,generic-cards,sideways9,sideways9-final}`.
- `tmp/r3/`: `reads/` (rotated199 = first fresh read with 6b681738, superseded; vertical9 and unread8 =
  final-rule reads; combined-final.json = readings used), `corpus525/`, `corpus9/`, `corpus-monex/`,
  `corpus-cards/`, `results-final-merged.json`, `visual.md`, surveys and dev tools (survey.py, route.py,
  routediff.py, genonly.py, memsim2.py, actions.py, famtable.py, postcheck.py, why.py, page.py).
