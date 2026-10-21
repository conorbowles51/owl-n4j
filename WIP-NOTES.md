# r13-merrick: work notes (counts and opaque ids only)

Branch `fin/r13-merrick`, based on 48e58b67 (fin/release-1 c835bdc8 + workfile). Not pushed. Private detail (real
values) only under /mnt/owl-data/fin-real (tmp/r13m/, bench/r13m-*, logs/r13m-*, truth-mini-r13m,
truth-backup-pre-r13m, truth-r13m-796).

STATUS: DONE. Three code commits plus this file. Whole set measured on 841cb268; the db9c3900 fix (proposal only,
no admission change) verified on the 17-document mini bench, the synthetic set and a read-only re-read of the run.

## Landed

| Commit | What |
|---|---|
| 99637db5 | Merrick cards: start from the printed days in the billing cycle; disputed Previous Balance established by the previous statement's New Balance; one held amount fixed by the printed balances; summary checks (unconfirmed payments total, several unconfirmed totals in a proven ledger, a lone point as a minus mark in backend checks only). |
| 841cb268 | Brokerage currency: cited proposal from the statement's holdings table (never confirmed automatically); the harness simulation re-reads a statement after the currency choice, as the product does; `rescore --resimulate`. |
| db9c3900 | Fix to 841cb268: the holdings currency was attached only to a completed reading, after the early return taken when the currency is unknown, which is the one case it exists for. On the whole run no batch item carried it. Found by checking the run database, not by any test; new end-to-end test fails on 841cb268. |

No reading revision change: the evidence engine's behaviour is unchanged (the lone-point sign mark is opt-in for the
backend's period checks; the engine's page pinning calls `summary_components` without it). Every bench uses
`--readings tmp/r12k/readings-v24b.json` unchanged (reading v24). No v25 bump from this unit.

## Item 1: Merrick (file d5a3ad9b75a08, 42 periods)

Root causes of the 19 held periods, established on the page text and on 300 dpi renders:
- Start not derived (7): the previous statement's closing date misread with its slash read as a digit (#2, #26, #37),
  the previous balance unreadable (#12), an off-cycle 20-day statement (#16), a new card number opening at 0 (#17), a
  91-day gap of quiet months (#31). Every one prints "Days in Billing Cycle"; the start is now closing - days + 1,
  basis `printed_day_count` (the engine's existing card basis). Every day count read on the file agrees with the
  truth chain. A previous statement that ends on any other day than start - 1 holds the period
  (`previous_statement_disagrees`), as do two candidates or a balance mismatch.
- Disputed Previous Balance (`$x?`, crop unconfirmed) on #3, #4, #8, #28: established when the previous statement's
  New Balance equals it (the opening agreement; it is outside the review revision and re-derived at import).
- #3 also has an unconfirmed Payments summary total: accepted only when it states exactly credits + the fixed amount.
- Lost decimal point on one ledger amount (#7, #24): pinned by the printed balances when it is the only held line,
  dated, not a payment, and the balance equation holds with it as a debit (`pinned_by_printed_controls`).
- #15: two unconfirmed summary totals; accepted only when the ledger is proven without them.
- #8 "valid-looking wrong date": the truth was wrong, not the product. The page prints the date the product proposed
  (confirmed at 300 dpi). The shared truth manifest row was corrected, with a note on the period (backup in
  truth-backup-pre-r13m). Valid-looking wrong values on wave 12 data are therefore 3, not 4.

Mini bench (bench/r13m-mini1, 17 docs: Merrick, credit-one, the 15 brokerage): merrick 23 -> 35/42 ready; credit-one
51 unchanged; 0 wrong, 0 critical, 0 valid-looking wrong values, no disagreement class in any ready period.

Still held (7): #8 (two held cells), #11, #27 and #28 (two held cells each, one equation cannot decide two), #1, #25,
#36 (statement date itself misread, plus balance or reading problems). A date-separator repair alone would make none
of these ready, so it was not built.

## Item 2: brokerage (15 periods)

(a) Holdings currency proposal. Only 2 of the 15 statements print a currency code in a holdings or money-market
table (d37df4b5e3403, d243eb0f0e749; on page 2). The other 13 print none (checked on the text layer, and visually on
a Kapital page). Prefilled: 1 of 15 (d37df4b5e3403#1, MXN, cited to page 2). d243eb0f0e749#1 already reads MXN by
itself, so it gets no hint. Counted in the product path (batch item summaries of bench/r13m-mini2, and a read-only
re-read of all 15 from the whole run's database on db9c3900). The earlier "2 of 15" in this unit came from a probe of
the detector, not the product path, and was wrong: see db9c3900. The proposal is cited to its page and cell, labelled
as printed in the holdings, and never confirmed automatically: ready stays 0 until a person confirms. In the
simulation d37df4b5e3403#1 then needs the currency decision alone (resolved), where the old simulation counted 7.

(b) Harness re-read after the currency choice. wave 12, same run, re-simulated with this code
(bench/r13m-w12sim, 297 corrections simulated again, 0 unread):

| | single | grouped | per 100 statements (796) |
|---|---|---|---|
| wave12 as run | 1946 | 1863 | 244 / 234 |
| wave12 rescored (old simulation) | 1786 | 1707 | 224 / 214 |
| wave12 rescored, re-read after currency | 1366 | 1268 | 172 / 159 |

Where it moves: intercam-brokerage 301/292 -> 83/64, kapital-brokerage 390/387 -> 8/1 (the old simulation counted
every ledger row of a statement read without a currency as a missing row). Elsewhere 8 periods change: the 5
non-brokerage currency-only periods (below), 2 andrews-share exact copies whose truth pairing changed in the rescore
(d1db0b3c9ca54#7, #8; previously dropped with 0 actions, now simulated: +92), and Merrick #8 (one fewer, the truth
fix). Ready counts are unchanged by construction (measurement only).

The 5 non-brokerage currency-only periods: d0b7a62995493#1 (wells-fargo), d466de5b7cc20#1 and d5b19fa643804#1
(santander-mexico), d997ce75a70a6#1 (bbva-mexico), df191ae7b7240#3 (monex-mexico); plus 1 unmatched item. All say
"Choose the currency printed on these statements." After the re-read: d466 and d997 now resolve
(18 -> 3 and 1 -> 4 actions); d0b7 (35 -> 88), d5b1 (17 -> 36) and df19 (4 -> 8) expose further row errors once read
in their currency. Whether any prints a currency the holdings proposal could cite, and why they lack a case or account
currency, was not investigated.

d243eb0f0e749#1: stays held. The engine reads no ledger lines from it at all, and holder, account and institution are
unread, so a printed 0.00 opening would not make it ready. Reason: reading, holder, account, institution, balance.

## Whole set (796 statements, truth-r13m-796 snapshot, readings v24b)

Product default (bench/r13m-whole2, frozen 841cb268) against wave12 rescored:
- Ready without edits 1404 -> 1416 of 1524 (+12, all merrick-card); recoverable 1416/1519. Ready periods lost: 0.
- merrick-card 23 -> 35/42 (target >= 32). credit-one 51/53 unchanged. Brokerage 0/15 unchanged (by design).
- Wrongly admitted 0. Critical-field errors in saved transactions 0 (22,502 saved from 1,427 periods). No proposal
  error class (money, date, account, currency, holder) in any ready period. Holder differs 0. Held kept out 5/5.
- Valid-looking wrong values proposed 4 -> 3 (date 1, amount 1, currency 1; target <= 3). The removed one is #8.
- Copies: 168/171 held automatically; the only copy offered or saved is the known dcfc8ce1f2afc#1 (the harness
  counts it once as offered and once as saved, so it prints "SAFETY FAILURE (exit 1): 2 exact copies", exactly as
  wave12 does). No new saved copy.
- Actions per 100 statements, single / grouped: 244 / 234 as run on wave12, 224 / 214 wave12 rescored, 172 / 159
  wave12 re-simulated (table above), 168 / 158 now (1335 / 1255).

Generic-only (bench/r13m-whole2-generic-only, LOUPE_FINANCIAL_GENERIC_ONLY=1) against wave12-generic-only rescored:
- Ready 1037 -> 1037; lost 0; wrongly admitted 0; critical 0 (17,913 saved from 1,047); held 5/5; holder differs 0;
  valid-looking wrong 1 -> 1 (currency); copies unchanged (only dcfc8ce1f2afc#1). merrick-card 0/42 (not detected
  without its layout, as before).
- Actions per 100: 694 / 665 as run, 554 / 531 rescored, 754 / 724 now (6002 / 5762). It rises: brokerage falls by
  600 actions as in product mode, but (1) 21 items re-paired in the wave12 rescore had their corrections dropped
  there and are simulated here (about +980), and (2) andrews-share currency-only periods, read again in their
  currency by the generic reader, expose row errors the one-action currency simulation hid (about +1,170). The
  higher figure is the honest one.

Synthetic (bench-runs/r13-merrick-final on 841cb268, and bench-runs/r13-merrick-final2 on db9c3900 with the same
engine readings; identical summaries): no safety failure (exit 0), 108/125 ready, recoverable 105/108, 0 wrong,
0 critical, held 10/10, copies 1/1, 0 valid-looking wrong values; holder differs 1 (the known
generic-v4-2025-04-scan-100dpi OCR letter).

Mini bench on db9c3900 (bench/r13m-mini2, 17 documents): ready 86/110 as on mini1, lost 0, 0 wrong,
0 critical, 0 valid-looking wrong; merrick 35/42; one batch item carries the printed currency (d37df4b5e3403#1).

## Tests (synthetic only)

- New or changed: test_financial_card_summary 22, test_financial_statement_import_merrick 37,
  test_financial_closing_only_period 27, test_financial_field_proposals 27, test_financial_benchmark_harness 21,
  test_financial_statement_currency 12; all OK. Nine related modules together on db9c3900: 308 OK.
- Engine pytest (merrick_automatic_repair, native_card_cell_ocr, statement_money_verification, financial_amount_ocr):
  102 passed.
- Full financial suite on 841cb268 (CHROMADB_PORT=1 CHROMA_PORT=1): Ran 6574, FAILED (failures=2, skipped=17). The
  2 are the known test_financial_unassigned_statement failures (batch_records_assignment_completion...,
  orphan_cannot_import...), present before this unit. 24 tests more than the 6550 baseline.
- Full financial suite on db9c3900: Ran 6575 (the 1 new test), FAILED (failures=2, skipped=17); the same 2 known
  unassigned_statement failures and nothing else.

## Unverified

- The shared truth manifest edit (#8 row date) was made after t-visual-v19 added a file to the same manifest. The
  integration session should check the edit survives any later truth write.
- The holdings proposal is shown in the queue path (batch summary / field proposals); the bulk currency dialog does
  not yet surface the hint.
- The whole set was not re-run on db9c3900 (nine hours). The fix adds a key to one early return and changes no
  admission, so ready, wrong and copy counts cannot move; it was measured on the mini bench and synthetic set.
- The 5 non-brokerage currency-only periods were not examined on the page (why no currency is established).
- The generic-only action increase is attributed by per-period diff to the two causes above; the per-cause figures
  are approximate (sums of per-period action differences, not cost-weighted).

## Next unit

- Merrick two-held-cell periods (#8, #27, #28): needs the engine's crop agreement to confirm one of the cells; the
  backend cannot decide two unknowns from one equation.
- Merrick statement-date misreads (#1, #25, #36): a slash-read-as-digit repair belongs in the catalog date reading
  (never in `merrick_statement`), and only helps together with the balance and reading fixes on those periods.
- d243eb0f0e749: the engine must read a ledger that has no opening line before anything else applies.
- The engine could adopt the `point_mark` sign mark (needs a reading revision bump; integration decides with
  r13-andrews, which may bump too).

## Decisions for Neil (each is one switch to reverse)

- `closing_only_period.MERRICK_DAY_COUNT`: a Merrick start from the printed days in the cycle, held if any previous
  statement disagrees. Reverse if a printed day count can be wrong on a statement that prints it.
- `card_summary.PIN_HELD_AMOUNT`: one held ledger amount fixed by the printed balances. Reverse if a single equation
  should never fix an amount.
- `card_summary.UNCONFIRMED_PAYMENTS_TOTAL` and `DOUBTFUL_TOTALS_WHEN_PROVEN`: unconfirmed summary totals accepted
  only where the ledger proves them.
- `summary_components(point_mark=True)` in backend checks only: a lone '.' between label and value read as a minus.
- The holdings-currency proposal (`field_proposals`, basis `printed_on_statement`): a proposal only, never confirmed.
- The harness re-read after the currency choice (measurement; changes no product behaviour).
