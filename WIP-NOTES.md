# r14-santander: work notes (counts and opaque ids only)

Branch `fin/r14-santander`, base 643d5ed5 (fin/release-1, real wave 13 integrated). Nothing pushed, nothing
deployed, nothing live written. No evidence-engine change: reading revision not bumped, readings
`tmp/int13/readings-w13.json` used unchanged. Frontend not touched (no frontend gate run).

## Landed

| Commit | Item | Engine / library | What |
|---|---|---|---|
| 170f8a08 | 1 | backend (Andrews) | A closed share section proven without activity (`closed_without_activity`) now offers `proven_closing`: balance 0, `printed: False`, basis `closed_without_activity`, cited to the closure notice row (page, rectangle) and the opening row the proof names. Admission records it in the saved admission record only while the source proof still applies. No balance row is invented. Switch `statement_import_andrews.CLOSURE_CLOSING`. |
| 57d10c64 | 2 holder | engine (general) | Unanchored holder: a page-1 addressee line read only into its company legal form ('NAME SA', rest lost) is completed from a heading line that is the top line plus more words, ends in a whole legal form beginning inside the top line after at least one word of the name, and is printed identically on at least two other pages. Switch `statement_engine.LEGAL_FORM_COMPLETION`. |
| 53420544 | 2 money | library (Santander) | (a) The date/folio column rule read as ')', '(', ']' or '[' separates date and folio like '|' and '/' (`RULE`). (b) A section whose SALDO FINAL line was not read takes its closing from the cover's balance summary line for the same account number, only when its previous-month value equals the printed opening and its current-month value equals the last movement's printed running balance (`COVER_CLOSING`, basis `cover_balance_summary`, printed and cited to its own cell). |
| 4809750c | 2 money | library (Santander) | A ruled row merging the last payment with the TOTAL line is split: two-line money cells give line 1 to the payment and line 2 to the total; the payment's amount must come from a two-line cell; the one-line balance is the payment's only when previous balance +/- amount equals it exactly. Otherwise the row stays unresolved; the total figures are never taken as the payment's (before: the deposit total was proposed as the payment amount, a valid-looking wrong value kept out only by the balance hold). Switch `MERGED_TOTAL`. |

Every rule fails closed and is switchable in one place.

## Decision taken (reversible in one line)

- **Item 1, where the proven closing lives.** The saved period's `closing_balance_source` stays `absent`: the
  schema allows only printed / carried_forward / absent (DB CHECK constraint `ck_financial_statement_periods_
  closing_source`), a proven-but-unprinted closing is none of them, and extending the enum needs a migration,
  which this unit may not write. The proven closing is carried on the proposal (`proven_closing`) and stored
  with the saved record (`statement_import_original` and `statement_admission.proven_closing`), with its basis
  and citation; the comparison (real_compare.proposal_view) reads a printed closing row first, then
  `proven_closing`. Reverse: `CLOSURE_CLOSING = False`. Would change it: Neil allowing a migration that adds a
  `proven` balance source, after which the period column can store 0 with that source.

## Measured

Readings: `tmp/int13/readings-w13.json` unchanged (no evidence-engine change; reading v24, v25 on Andrews).
Code of every whole-set run: frozen copy `bench-code/r14s-4809750c` (= branch head before these notes).
Truth: a snapshot of the manifest taken at the unit's start (`tmp/r14s/truth-snap`, 797 documents, the same
manifest bench/wave13 was scored on), so before/after are like-for-like; then the final runs rescored against
the current manifest (changed during the wave by the truth units: +18 all-unverified documents, unscored; 20
OCR-reconciled periods now verified).

Whole set, product default (bench/r14s-whole) against bench/wave13, same truth snapshot:

| | wave13 | r14-santander |
|---|---|---|
| Ready without edits | 1,645 / 1,729 | **1,654 / 1,729** (+9, all santander-mexico; 0 lost) |
| Recoverable ready | 1,645 / 1,724 | 1,654 / 1,724 (95.9%) |
| santander-mexico ready | 128 / 146 | **137 / 146** (target 138: **1 short**) |
| Santander blocking reasons | balance 8, reading 7, holder 7, currency 2, account 1, institution 1, not_detected 1 | reading 6, balance 5, currency 2, holder 1, account 1, institution 1, not_detected 1 |
| Wrongly admitted / critical-field errors | 0 / 0 (25,489 rows) | **0 / 0** (25,808 rows from 1,665 saved periods) |
| Duplicate ledger contributions / printed periods saved twice | 0 / 0 | 0 / 0 |
| Must-hold kept | 5 / 5 | 5 / 5 |
| Exact copies held / offered / saved | 168 / 1 / 1 | 168 / 1 / 1 (only dcfc8ce1f2afc#1; no new copy saved) |
| Valid-looking wrong values proposed | 3 | 3 (the same: bbva date 1, amount 1; scotiabank currency 1) |
| Classes in READY periods | holder_differs 36 (BBVA same entity), holder_missing 6, closing_balance_missing 3, repeat_offered 1 | holder_differs 36 (the same 36 periods), holder_missing 2 (d3df70b5f4085#1, d3f7377e8f85d#1, not Santander-unit periods), repeat_offered 1 (the copy). **No balance, money, date, account or currency class in any ready period** |
| Investigator actions, one at a time / grouped | 1,095 / 1,020 | **1,058 / 996** |
| Actions per 100 statements (797) | 137.4 / 128.0 | **132.7 / 125.0** |
| Santander actions, one at a time / grouped | 393 / 375 | **356 / 351** (target <= 200: **not met**) |

Gained periods, by rule and by who serves them in the run:
- engine rule (LEGAL_FORM_COMPLETION): d6ad9634fb4ff#1, d8ce041307299#1, dc1e430221a20#1, dc1e430221a20#2
  (engine-served), d6f43c4078e3a#1, d7ecc8297e894#1 (library-served once the engine reading agrees). The 4
  ready zero-balance sections of the same statements (#2) that were saved without a holder now carry it.
- library rules: d0c644cd5f5f7#1 (RULE), d39807b9095f7#2 (COVER_CLOSING), dbbf41233fbf9#1 (MERGED_TOTAL).
- Santander ready served engine 86 / library 51.
- Item 1: d730f3e0d171f#66, #67 and da162973a4fa0#37 stay ready and now carry closing 0.00 (comparison
  agrees; no class).

Generic-only (bench/r14s-whole-go, `LOUPE_FINANCIAL_GENERIC_ONLY=1`) against bench/wave13-generic-only:
1,242 -> **1,250 / 1,729**, 0 lost, **0 wrongly admitted**, 0 critical (18,981 rows), holds 5/5, copies: only
dcfc8ce1f2afc#1 offered and saved (as before); gained 8 santander (the 6 holder periods, dec355946865b#1, #2);
ready-period classes: holder_differs 2 (the same two as wave13), holder_missing 4 (was 8). Actions 6,002 /
5,762 -> 5,986 / 5,762 (751 / 723 per 100).

Rescored against the CURRENT manifest (815 documents; 1,740 distinct scored periods): product **1,664 / 1,740**
(recoverable 1,664 / 1,735), 0 wrong, 0 critical (25,857 rows), santander 137 / 146; generic-only **1,259 /
1,740**, 0 wrong. Only saved copy: dcfc8ce1f2afc#1 (exit 1 in every real run, product and generic-only, as in
every wave since 9). The rescore does not re-simulate corrections, so its action totals are not comparable.

Shared compare dir: updated with the final product run rescored against the current manifest, for the 797
documents this run read (backup `compare-backup-pre-r14s`); the 18 newly added documents' files were left as
the truth units wrote them.

Synthetic (bench-runs/r14-santander-final2, code 4809750c): **108 / 125, BENCH_EXIT=0**, recoverable 105/108,
0 wrong, 0 critical (366 rows), holds 10/10, copies 1/1, 0 valid-looking wrong values. (Also run on 53420544:
identical.)

Mini runs (private): bench/r14s-mini-san-{a,b,c} (the 16 Santander documents: 7 -> 15 -> 16 of 25 ready, 0
wrong), bench/r14s-mini-and-a (the 2 Andrews documents of item 1: 181/184 ready, identical per period to
wave13, the 3 closed sections now carry closing 0).

## Tests actually run

- Targeted: test_financial_andrews_no_activity 33 OK (5 new); test_financial_statement_engine 236 OK (2 new);
  test_financial_statement_import_santander 14 OK (6 new).
- Full financial suite (live .venv, CHROMADB_PORT=1 CHROMA_PORT=1, CLAUDE.md command), on 4809750c: **Ran
  6,610, FAILED (failures=2, skipped=20)**: only the 2 known test_financial_unassigned_statement failures. (On
  53420544: Ran 6,608, the same 2.)
- Frontend: not touched, not run.

## Not done / still held (santander-mexico, 9 periods; all expected auto)

- The older scanned layout ("estado de cuenta integral", 4-page scans, one client; 7 periods): d9fd8282f829e#1
  (engine: unplaced_money_line, a month read as letters, separators damaged in amounts and balances),
  dfebde69177c4#1 and da46a3c8e4979#1 (not_reconciled; da46 also no_opening), d4394c6b6d780#1 (no_geometry;
  holder too), d8af2d5c29493#1 (no_opening; account, institution), d466de5b7cc20#1 and d5b19fa643804#1
  (currency: this layout prints no MONEDA line; the engine reads no ledger at all, the library does not
  recognise the layout because its period prints as 'PERIODO : dd AL dd DE <month> DE yyyy'). Every one has
  several independent OCR defects; no single general rule unlocks them. Next: a library profile for this
  layout (period line, cover summary, movement columns) plus digit-only money agreement pinned by the
  printed running balance (all digits read, only separators damaged, previous balance +/- amount = balance).
  The currency must then come from a printed fact (no MONEDA is printed on this layout; '$' alone is not
  evidence, by design).
- dbbf41233fbf9#2 (reading, 56 rows, 113 actions): the investment section's ruled tables on a native page
  are read with several printed lines merged into one row (two or three balances in one cell), so the
  continuation pages are not attached and no row parses. Needs the evidence engine to rebuild rows of a
  native page's ruled table from the text layer's word positions (reading revision bump, fresh reads).
- d8b0192c926db#1 (not_detected): the cheque section's ruled table kept only its outline
  (`table_rectangle_only`, every cell unlocated), so the Santander reader skips it. Same evidence-engine fix.
  Only 3 Santander truth documents have such a table.
- Santander actions 356: the 2 periods above (dbbf#2 113) and the 7 scans carry nearly all of them.

## Next unit

1. Evidence engine: ruled tables on native pages rebuilt from word positions where cells are unlocated or
   hold several printed lines (dbbf41233fbf9#2, d8b0192c926db#1; bump the reading revision, fresh-read the
   affected documents).
2. The older scanned Santander layout (7 periods) as above.

## Decisions for Neil (none blocking)

- Item 1: a `proven` balance source for the saved period needs a migration (see Decision taken). Recommend:
  add it with the next migration-bearing release; until then the proven closing lives in the saved record.
- MERGED_TOTAL fixes a valid-looking wrong value the Santander reader proposed (a TOTAL figure as a payment
  amount); it was always held by the balance check, so no saved statement was affected.
