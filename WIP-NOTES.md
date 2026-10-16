# t-visual-v05 — WIP notes (counts and opaque ids only)

Unit: visual ground truth for visual-queue shard v05 (`santander-mexico`: 40 documents, 331 pages; 35 vector-outline
documents with no usable text layer, 5 digital documents whose text-layer truth was `unverified`), and the BLIND
measurement of fin/release-1 after integrate-7 (d5985a0a, no tuning) on every new verified period. Branch
fin/t-visual-v05 from fin/release-1 d5985a0a. Not pushed. **No code changed at all** (processor or tooling): the
existing real_visual format covered every page. Private detail: /mnt/owl-data/fin-real/truth/visual/PROGRESS-v05.md
(per-document status, conventions, copies, chain, blind findings), truth/visual/<doc>.txt|.json, tmp/v05/ (renders,
tesseract typing aid, draft/fix/asm/chk/chain/query helpers, mini-compare), logs/v05-*.log, truth-mini-v05,
bench/v05-mini (blind fresh read), bench/wave7-v05 (rescore copy), audit-v05; backups truth-backup-pre-v05/,
compare-backup-pre-v05/.

## Landed (commits)

- (this commit) WIP-NOTES.md only. Truth itself is private (never committed).

## Classification and truth (steps 1-3)

- Every page of all 40 documents rendered with fitz and read with the Read tool (100 dpi full pages, 130 dpi for the
  query printouts, 200 dpi crops where a figure needed it). Tesseract text was a typing aid only: a draft per
  document, then every row, balance and summary figure checked against the page image, and every value the draft
  left unread or unsigned typed from the image (row-level corrections per document kept privately in tmp/v05/work).
  Each period's printed controls (summary box: Saldo inicial, +Depositos, -Retiros, Saldo final) were typed
  separately from its rows, so the check stays independent; every printed running balance is checked by the compiler.
- **Documents by final status: verified 35, unverified 5.** not_statement 0, incomplete 0.
  Page kinds (331): statement pages with summary or movements, plus fiscal-information / abbreviation / notice pages
  (`skip`, no statement values). Every document prints "Pagina n de N" and every printed page is present.
- **Periods: 71 = verified 66 + unverified 5.** Incomplete 0. The 66: 31 documents x 2 sections (cheques account +
  "Inversion Creciente" investment section, the same convention as the existing Santander digital truth: the
  investment section is its own period under its own printed account number), 4 dollar-account documents x 1.
- Each verified period: opening + every row = closing to the cent; every printed running balance matches; the
  summary box deposits and withdrawals totals equal the rows (and the movement table's printed TOTAL row). These
  statements print no item counts.
- **Copies: 6 pixel-identical pairs inside the shard** (render hash equal on every page at 40 and 60 dpi; different
  bytes, issued seconds apart), 12 periods marked `duplicate` by real_truth. **0 periods duplicate any of the 52
  Santander documents verified earlier.**
- **Expected: auto 54, decision 0, duplicate 12.** Holder, account, dates and currency printed on every period.
  Dollar-account periods: no movements; the printed list of "commissions pending payment" is not a movement and not
  charged (same convention as the earlier dollar-account truth).
- **The 5 digital `unverified` documents (online movement queries, "Consulta de Movimientos"): the visual reading
  confirms them, it does not settle them.** Each image agrees with the text layer value for value; the text-layer
  truth did not fail by misreading. It failed because the bank prints "Saldo Inicial" as the balance after the
  first listed movement (all 5), so printed opening + rows differs from the printed closing by exactly that
  movement. With the opening derived (first printed balance minus the first movement) all 5 reconcile, including the
  printed credit/debit counts, totals and movement count. They stay `unverified` (reason: printed Saldo Inicial is
  the balance after the first listed movement; the opening before it is not printed), per t-truth decision 2.
  They are now reviewed visually, so the queue counts them done; the account is recorded as printed (full number)
  instead of the text-layer reader's last 4 digits (unscored either way).
- **Statement documents final: 688/832 -> 723/832** (35 vector documents verified; the 5 unverified were already
  final). Status over 832: verified 698, settled 2, unverified 18, not_statement 5; pending needs_visual 93,
  needs_parser 13, partly_verified 3. Truth periods verified 1,494 -> 1,560. Santander documents: verified 52 -> 87,
  unverified 13, ?santander needs_visual 55 -> 20 (shard v06), not_statement 1. visual-queue.json: **v05 done
  (40/40)**; queue done 193 -> 233.

## Santander chain (independent cross-check, all Santander truth)

- 127 verified periods (114 distinct printed periods after collapsing copies) over 6 printed accounts.
  **72 adjacent pairs, all chain (opening = previous closing), 0 contradictions, 0 overlaps** (37 pairs have a v05
  side). 32 date gaps remain (statements in shard v06 or not in the productions).

## BLIND processor measurement (step 5; fin/release-1 d5985a0a after integrate-7, no tuning)

Mini corpus truth-mini-v05 (35 PDFs, 66 periods = 54 distinct + 12 exact copies; the 5 unverified documents are not
in the manifest), fresh read, run_real_benchmark --concurrency 2, OMP_THREAD_LIMIT=1, product default (automatic
save ON), compare into tmp/v05/mini-compare (private). The box was NOT quiet (load 6 before reading, 10.5 after;
r8 units were reading): the time-budgeted money-cell consensus can lose a repair under load (held, never wrong), so
the ready figure is a floor.
- **Ready 28/54 (51.9%), all 28 saved by the system with no click. Wrong admissions 0.** Critical-field errors 0
  (986 rows saved from 28 periods), duplicate ledger contributions 0, valid-looking wrong values proposed 0, batch
  items matched to no truth period 0, previously ready lost: n/a (first read of these documents).
  Exact copies held automatically 9/12; the other 3 copies were held for reading/balance (not admitted).
- **Engine-served 3, library-served 25.**
- Held 26 (exact reason sets): holder only 10; balance+reading+readiness_update 6; holder+balance+reading 2;
  currency 2; no_activity+readiness_update 2; balance+readiness_update 1; balance+reading+duplicate 1; balance 1;
  balance+no_activity+readiness_update 1. Overlapping: balance 12, holder 12, readiness_update 10, reading 9,
  no_activity 3, currency 2, duplicate 1. Actions 210 single / 181 grouped (field edits 75, decisions 5, rows to
  add 55).
- **Identity against truth (54 detected periods, field by field): 0 values differ anywhere.** period start 54/54,
  period end 54/54, account 54/54, currency 52/54 (2 unread), holder 42/54 (12 unread), opening 51/54 (3 unread),
  closing 49/54 (5 unread). Rows: 1,698 in truth, 1,629 matched exactly, 0 differing, 67 missing / 21 extra.
- Classes (all fail closed):
  1. **Holder unread, 12 periods** (d469232ad20d3#1 d51429014b8a2#1 d82fc57384562#1 d8dc5a82aa802#1 (dollar
     accounts), d6ad9634fb4ff#1-2 d6f43c4078e3a#1-2 d7ecc8297e894#1-2 d8ce041307299#1-2). Root cause from
     source: `statement_engine.address_holder` takes the holder only from an address block ending in a postal-code
     line; on these pages the engine's page-1 reading has the postal line (dollar accounts) or the name line
     (the others) damaged, so no block qualifies. 10 periods wait on this alone: one grouped holder confirmation per
     account would admit them. r8-mt-engine's holder rule work is the place to measure it.
  2. **Rows unread or missing on long cheques sections, 10 periods** (d0c644cd5f5f7#1 d0edd29dc8159#1
     d2aca556b8f32#1 d2c5696820962#1 d7d1158e6b261#1 da105e0636d75#1 d6ad9634fb4ff#1 d8ce041307299#1
     d39807b9095f7#1, d3483fa04f746#1 balance only), plus d39807b9095f7#2 (investment section, balance).
  3. **Currency unread, 2 periods** (d41406d5f952c#1-2).
  4. **Zero-activity investment sections held for a no-activity confirmation, 3 periods** (d239ddd4963c3#2
     d9e5f74bcd469#2 d96fb96106d3c#2) although the summary prints zero deposits/withdrawals and equal balances
     (other zero sections in the same shard were admitted).
  5. readiness_update appears on 10 held periods (the measurement gap handed to r8-import-ops); none is held by it
     alone.

## Rescore of the bench of record with the new truth (no re-read)

Copy bench/wave7-v05 of bench/wave7, harness --rescore at d5985a0a, compare/ shared (backup compare-backup-pre-v05/):
- **1,147/1,397 ready** (was 1,147/1,343: denominator +54 = the new distinct Santander periods, `not_detected` by
  absence because wave 7 never read these documents), recoverable 1,147/1,393, **wrong 0**, critical 0 (17,948
  rows), held kept out 4/4, exact copies 148/165 (+12 = the v05 copies, unread), unmatched items 16 (0 offered).
  **Ready lost 0, gained 0.**
- **Compare: statements compared 668 -> 703** (of 827), periods+items 1,532 -> 1,598, without disagreement
  1,291 -> 1,289. The -2 is not this truth: the only existing compare files that changed are d0f81a5b856d7
  (andrews) and df7e9c5f8cbb0 (capital one), the rescore re-pairing artefact t-visual-v15/v16/v17 describe.
  Actions 2,094 -> 2,171 single / 1,840 -> 1,918 grouped (the 54 unread periods).
- A first rescore attempt was killed by the tool time limit before writing anything (compare/ verified identical to
  the backup); the rerun ran detached and completed.

## Live ledger (read-only audit audit-v05; READ ONLY transaction; nothing written)

- **On v05 documents: 16 live admitted periods on 15 documents: agrees 15, live_period_undated 1 (d9e5f74bcd469),
  disagrees 0, must be held 0.**
- All truth documents: 842 live admitted periods: disagrees 5 (the same 5 ids as waves 5-7), must be held 0. Same
  printed period admitted twice in a case: 0.

## Tests actually run

- test_financial_benchmark_corpus + real_compare + real_visual + real_truth + statement_census: **104 OK**
  (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1, pdfplumber from headless/real/pylib). No code changed in this unit.
- Synthetic benchmark not run: no code changed (processor or tooling), so it cannot move; the box was at load 6-11
  with r8 units reading.
- Full financial suite not run: no module changed.

## Next units should continue with

- Santander reader work, measured on truth-mini-v05 (54 distinct periods, 28 ready today, 0 wrong): (1) holder from
  a damaged page-1 address block (12 periods; 10 alone), together with r8-mt-engine's holder rule; (2) rows on long
  cheques sections (10 periods, 67 missing / 21 extra rows); (3) zero-activity investment sections (3);
  (4) currency (2). Re-run the blind read at low load before quoting the figure as final.
- Truth coverage: v06 (the other 28 Santander documents; 20 still needs_visual, closes most chain gaps), v01/v02
  (BBVA), v04 (Kapital), v03 (Intercam), v09, v11/v12, v14, v18, v19.
- Integration: per-family tables gain 54 distinct Santander periods (santander-mexico 60 -> 114 distinct verified);
  the headline denominator grows by 54 until the next full read covers them.

## Decisions needed from Neil

- None. Decided here with reasoning (private transcription, reversible in one place): the 5 online movement queries
  stay unverified (opening not printed; reverse: derive the opening, all 5 then reconcile including printed counts);
  their account is recorded as printed in full (reverse: last 4 digits as the text-layer reader did).
