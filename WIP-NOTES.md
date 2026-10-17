# t-visual-v06 — WIP notes (counts and opaque ids only)

Unit: visual ground truth for visual-queue shard v06 (`santander-mexico`: 28 documents, 160 pages; 20 vector-outline
documents with no usable text layer + 8 digital documents whose text-layer truth was `unverified`), plus the small shards
v09 (2 documents, issuer unknown), v14 (monex / scotiabank, 2) and v18 (wells-fargo, 1); then the BLIND measurement of
fin/release-1 after integrate-8 (cf932651, no tuning) on every new verified period. Branch fin/t-visual-v06 from
cf932651. Not pushed. **No code changed at all** (processor or tooling): the existing real_visual format covered every
page. Private detail: /mnt/owl-data/fin-real/truth/visual/PROGRESS-v06.md (per-document status, copies, chain, blind
findings), truth/visual/<doc>.txt|.json, tmp/v06/ (renders, tesseract typing aid, draft/fix/asm/chk/chain/query/rhash
helpers, mini-compare), logs/v06-*.log and audit-v06.log, truth-mini-v06, bench/v06-mini (blind fresh read),
bench/wave8-v06 (rescore copy), audit-v06; backups truth-backup-pre-v06/, compare-backup-pre-v06/.

## Landed (commits)

- (this commit) WIP-NOTES.md only. Truth itself is private (never committed).

## Classification and truth (steps 1-3)

- Every page of all 33 documents rendered with fitz and read with the Read tool (100 dpi full pages; 110-170 dpi crops
  where a figure needed it; 120 dpi for the online queries). Tesseract text was a typing aid only: a draft per
  document, then every row, running balance and summary figure checked against the page image; row values the
  draft left unsigned or unread were typed from the image (15 corrections). Each period's printed controls (summary box: Saldo inicial,
  +Depositos, -Retiros, Saldo final; equal to the movement table's TOTAL row) were typed separately from its rows.
  For the 8 online queries the pdfplumber text layer was the typing aid; the image agrees with it value for value.
- **Documents by final status (33): verified 24, unverified 8, settled 1** (verified + incomplete). not_statement 0.
  - v06 (28): 17 vector originals verified; **3 vector documents are pixel-identical copies of v05 documents**
    (render hash equal on every page at 40 and 60 dpi, different bytes): dbc494dc292a2 = d0edd29dc8159,
    dfedd74a4d11b = d4651ecaf07e7, dca039f8d55bd = d5d6c5a17d6c1; transcription copied, periods `duplicate`.
    0 copies of the other 84 verified Santander documents.
  - v09: dfebde69177c4 is **santander-mexico** (scanned certified copy of an integral statement; the stamp covers no
    value); dfefec6e0fe91 is **monex-mexico** (pages drawn sideways). Issuer decided from the page.
  - v14: db26d3e08b2d9 monex-mexico (MXN + EUR sections, no movements); dc3fbbaef34d0 scotiabank-mexico (account opened
    in the period, zero activity, summary all zero).
  - v18: d0b7a62995493 is **not** a not_statement: it is a fragment of a statement, printed pages 2 and 3 of 6. The
    checking period is complete on those pages (summary box, every row, printed Totals row) -> verified; the savings
    account's own page (printed page 4) is not in the file -> `incomplete` (hold).
- **Periods (53): verified 44, unverified 8, incomplete 1; of the verified, duplicate 6.** Rows transcribed 983
  (v06 vector originals 480 incl. investment sections, copies 334, online queries 123, v18 32, v09 14, v14 0).
  Verified periods by document kind: Santander cheques + "Inversion Creciente" investment section (own period, own
  printed account) 14 documents x 2, Santander dollar accounts 3 x 1, Santander integral statement 1, Monex 2 x 2,
  Scotiabank 1, Wells Fargo checking 1.
- Each verified period: opening + every row = closing to the cent; every printed running balance matches; the printed
  deposits and withdrawals totals equal the rows. These statements print no item counts (the queries do; see below).
- **Expected: auto 38, decision 0, duplicate 6, hold 1.** Holder, account, dates and currency printed on every period.
- **The 8 digital `unverified` v06 documents: the same online movement-query class as v05's five, not something the
  visual reading settles.** All 8 are "Consulta de Movimientos" printouts of one account; in all 8 the printed
  "Saldo Inicial" equals the balance after the first listed movement. With the opening derived (first printed balance
  minus the first movement) all 8 reconcile, including the printed credit/debit counts, both totals and the movement
  count. They stay `unverified` (reason: printed Saldo Inicial is the balance after the first listed movement; the
  opening before it is not printed), per t-truth decision 2; now reviewed visually, so the queue counts them done.
- **Statement documents final: 723/832 -> 748/832** (+25 = the 24 verified + 1 settled; the 8 unverified were already
  final). Status over 832: verified 722, settled 3, unverified 18, not_statement 5; pending needs_visual 68,
  needs_parser 13, partly_verified 3. Truth periods verified 1,560 -> 1,604. santander-mexico documents: verified
  87 -> 108, unverified 13, not_statement 1 (no Santander document left pending). monex-mexico 87 verified (206
  periods), scotiabank-mexico 8. visual-queue.json: **v06, v09, v14, v18 done**; queue done 233 -> 266 of 353.

## Santander chain (independent cross-check, all Santander truth)

- 165 verified periods (146 distinct printed periods after collapsing copies) over 6 printed accounts.
  **122 adjacent pairs, all chain (opening = previous closing), 0 contradictions, 0 overlaps** (50 pairs have a side
  from this unit). **Gaps 32 -> 14**: the 14 left are months with no monthly statement in the productions (by account: 6 and 3 on one
  cheques account and its investment section, 2 and 2 on another, 2 on the account whose missing months are covered
  only by the unverified online queries, 1 on a dollar account).
- Monex: both new Monex periods and the new v09 Monex statement fill one-month gaps in their contract's existing chain
  (equal balances on both sides); the v09 Santander integral statement fills the October -> December 2022 gap of its
  account (opening = October closing, closing = December opening).

## BLIND processor measurement (step 5; fin/release-1 cf932651 after integrate-8, no tuning)

Mini corpus truth-mini-v06 (28 PDFs: the 25 documents of this unit with scored periods + the 3 v05 originals of the
copies so exact-copy holding can be judged; 51 periods = 45 distinct + 6 copies; the 8 unverified queries are not in
the manifest). Fresh read, run_real_benchmark --concurrency 2, OMP_THREAD_LIMIT=1, product default (automatic save
ON), compare into tmp/v06/mini-compare (private). **The box was NOT quiet** (load 3.5 before reading, 9.2 after;
another unit's full read ran alongside): the time-budgeted money-cell consensus can lose a repair under load (held,
never wrong), so the ready figure is a floor.
- **New periods: ready 12/38 auto (31.6%), all saved by the system with no click. Wrong admissions 0.**
  Critical-field errors 0 (95 rows saved from 13 periods), duplicate ledger contributions 0, valid-looking wrong values
  proposed 0, batch items matched to no truth period 0. Must-hold kept out 1/1 (the Wells Fargo savings fragment, not
  detected at all). Exact copies held automatically 5/6 (the 6th held for reading/balance, not admitted).
- **Engine-served 4 (all Monex), library-served 8 (santander-mexico-movements).**
- The 3 v05 originals in this mini corpus: 1/6 ready (wave 8 bench: 1/6) — the known v20-reading Santander regression
  STATE.md records (unread closing balance), r9-engine-santander item 1.
- Held 26 new periods (exact reason sets): balance only 7; currency only 5 (db81fa7b3efaf#1-2, dec355946865b#1-2,
  d0b7a62995493#1); reading+balance 5 (dc0358851f35e#1, dca2387d4d6e0#1, dcefe35abd828#1-2, de2a15c3bd1a5#1);
  holder only 4 (dace03b63ce7f#1, dde48542b0cb5#1, df4f88f1870cb#1 — the three dollar-account statements — and
  dc1e430221a20#2); balance+no_activity 2 (dc0358851f35e#2, dc5c384109d9c#2); reading+holder+balance 2
  (dc1e430221a20#1, dfebde69177c4#1); reading+institution+balance 1 (dc3fbbaef34d0#1, scotiabank).
  Balance-only 7: dc4246e6441dc#1, dc5c384109d9c#1, dca2387d4d6e0#2, dd7d0ecc49ddb#1, ddded5f818873#2,
  df69785102607#1, de2a15c3bd1a5#2.
- **Identity against truth (38 new auto periods, field by field): 0 values differ anywhere.** period start 38/38,
  period end 38/38, account 38/38, currency 33/38 (5 unread), holder 31/38 (7 unread), opening 33/38 (5 unread),
  closing 21/38 (17 unread). Rows: 526 in truth, 398 matched exactly, 126 missing / 29 extra; 2 rows flagged
  "differing" are not value differences: one amount unread (dca2387d4d6e0#1) and one pairing of three equal-amount rows
  on one day (dcefe35abd828#1, the read row carries its own correct balance); both periods held.
- Classes (all fail closed): (1) closing balance unread on Santander cheques/investment sections (17 periods; the v20
  regression); (2) currency unread (4 Santander periods on 2 documents of one holder, plus Wells Fargo 1); (3) holder unread on the 3 dollar-account statements (the v05 class: address block not taken);
  (4) rows missing on long cheques sections (5); (5) zero-activity investment sections held for a no-activity
  confirmation (2) although the summary prints zero movements and equal balances.

## Rescore of the bench of record with the new truth (no re-read)

Copy bench/wave8-v06 of bench/wave8 (the integrate-8 bench of record), harness --rescore at cf932651, compare/ shared
(backup compare-backup-pre-v06/; the rescore ran detached, about 80 minutes at load 7-9):
- **1,252/1,436 ready** (was 1,252/1,397: denominator +39 = the 38 new distinct auto periods + the 1 must-hold period,
  `not_detected` by absence because wave 8 never read these documents), recoverable 1,252/1,431, **wrong 0**,
  critical 0 (19,074 rows), held kept out 5/5 (+1, the Wells Fargo savings fragment), exact copies 159/171 (+6 = the
  v06 copies, unread), unmatched items 16 (0 offered). **Ready lost 0, gained 0** (family table on the original 1,397).
- **Compare: statements compared 703 -> 728** (of 827; +25 files, all this unit's scored documents; the 8 unverified query documents
  are not in the bench corpus, so not compared), periods+items 1,598 -> 1,643, without disagreement 1,393 -> 1,392. The -1 is not this truth:
  the only existing compare files that changed are d0f81a5b856d7 and d1db0b3c9ca54 (andrews-share) and df7e9c5f8cbb0
  (capital-one-card), the rescore re-pairing artefact t-visual-v05/v15/v16/v17 describe (only d0f81a5b856d7 changes
  its no-disagreement count, 11 -> 10). Actions 1,336 single / 1,240 grouped on the rescored copy.

## Live ledger (read-only audit audit-v06; READ ONLY transaction; nothing written)

- **On this unit's documents: 13 live admitted periods on 12 documents: agrees 9, live_period_undated 4
  (db26d3e08b2d9, dc3494dd3b7fa, dc4246e6441dc, df69785102607), disagrees 0, must be held 0.**
- All truth documents: 855 live admitted periods: agrees 453, convention_only 301, live_period_undated 96, disagrees 5
  (the same 5 ids as waves 5-8). Same printed period admitted twice in a case: 0.

## Tests actually run

- test_financial_benchmark_corpus + real_compare + real_visual + real_truth + statement_census: **109 OK**
  (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1, pdfplumber from headless/real/pylib). No code changed in this unit.
- Synthetic benchmark not run: no code changed (processor or tooling), so it cannot move; the box was at load 7-11
  with another unit reading.
- Full financial suite not run: no module changed.
- Neil decisions 2026-10-09 (Andrews sign, late-posted card charges): not touched by this unit (no processor code;
  no Andrews or card documents in these shards).

## Next units should continue with

- r9-engine-santander: measure on truth-mini-v05 + truth-mini-v06 (54 + 38 new distinct periods). Priorities from v06:
  (1) closing balance unread (17 periods, the v20 regression); (2) currency unread (4 periods, 2 documents); (3) holder on dollar-account statements (3); (4) rows on long cheques sections (5);
  (5) zero-activity investment sections (2). Re-run the blind read at low load before quoting the figure as final.
- Scotiabank (1 period: institution + reading on a zero-activity new account) and Wells Fargo checking (currency
  unread; family has no reader) are single-document classes.
- Truth coverage: v01/v02 (BBVA, 49 documents), v04 (Kapital, 24), v03 (Intercam, 10), v11/v12 (Capital One confirm),
  v19 (Navy Federal, 345 pages). No Santander document is pending any more.
- Integration: per-family tables gain 38 distinct new verified periods (santander-mexico +31, monex +4, scotiabank +1,
  wells-fargo +1, plus the must-hold Wells Fargo savings period); the headline denominator grows by them until the next
  full read covers them.

## Decisions needed from Neil

- None. Decided here with reasoning (private transcription, reversible in one place): the 8 online movement queries
  stay unverified (opening not printed; reverse: derive the opening, all 8 then reconcile including printed counts);
  the Wells Fargo fragment's checking period is verified on the two pages present and its savings period is
  incomplete/hold (reverse: mark the whole document incomplete).
