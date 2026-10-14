# r6-synchrony — WIP notes (real wave 6) — complete

Counts and opaque ids only. Private detail (dev tools, engine/routing surveys, frozen code, run databases,
per-statement comparisons) under `/mnt/owl-data/fin-real/tmp/r6s/` and `/mnt/owl-data/fin-real/bench/r6s-*`.
Branch `fin/r6-synchrony`, based on fin/release-1 fb8abfdf. Not pushed, nothing merged, no live data read or
written, no services touched. Backend only: no evidence-engine change, so no reading-revision bump and no
reader-recovery entry; every run reuses the wave-5 / v17 readings.

## Result in one paragraph

Synchrony card statements go from **0/16 to 16/16 ready without any edit**, every one served by the general
engine (plus a data-only institution profile); no Synchrony library reader was needed. All 47 rows equal truth
(date, amount, direction), all 16 opening and closing balances equal truth, all six summary lines and both
section totals are checked in every period, **0 rows inverted**. On the whole real truth set (583 documents,
1,253 distinct verified periods, wave-5 readings) ready goes **1,118 -> 1,134 (89.2% -> 90.5%)** with **0 wrong
admissions**, 0 critical-field errors, must-hold 4/4, and **0 previously ready periods lost** (16 gained, all
Synchrony). Synthetic 105/125, 0 wrong, exit 0.

## Landed

| Commit | What |
|---|---|
| eea33ee0 | General engine (details below) + `synchrony-card` institution profile (data) + day-count start in `closing_only_period` + import keeps that start out of the printed header; 13 engine tests, 5 closing-only tests |
| 63858885 | interim notes |
| (this) | final notes |

What the engine now reads (any issuer; nothing keyed to Synchrony except the profile's data):

1. **One-cell movement tables** (`_split_row`, `_line_row`): a drawn box with header cells but no row rules is
   stored as one cell holding every printed line. Under a heading naming date/description/amount columns, when
   every dated line carries its own amount, each printed line becomes a row (id `<page>:<table>:<row>:lineN`,
   citing its own band of the cell). Wrapped description lines join the movement above (`_continues`, same
   cell, next line); section headings, section totals, continuation notices and the year-to-date heading never
   do (`_not_description`). A dated line without its amount keeps the cell whole (existing multi-line entry rule).
2. **Side-by-side boxes on one stored row** (summary box beside payment box) are read box by box; a box under a
   PAYMENT INFORMATION heading (vocabulary) is never a control (`payment_box`).
3. **Card summary vocabulary**: NEW PURCHASES (debit component); net lines "+/- ... (net)" (`net_component`,
   signed as printed, added to the charges' side); the printed "+/-" mark is not label text.
4. **Section totals** (`SECTION_TOTALS`: TOTAL FEES / TOTAL INTEREST FOR THIS PERIOD) are controls on the lines
   under their section heading, in the engine proof and as the review's fee/interest-scoped statement totals
   (`charge_group` on their lines; the review arithmetic and admission re-check them). The year-to-date block
   (`YEAR_TO_DATE`) is neither movements nor controls.
5. **Closing-only period** (`_closing_only_period`): one labelled statement closing date + one printed "days in
   billing period" on the page. The start (closing - days + 1) is `period_start_basis=printed_day_count`: the
   statement metadata prints no start; `closing_only_period._day_count_dates` supplies it as **derived**
   (PeriodBounds start_source=derived, end printed) only when every previous statement for the same card in the
   case closed the day before (else held: `previous_statement_disagrees` / `several_previous_statements`); the
   engine applies the same check within one file (`period_start_contradicted`). Date order from the profile, or
   a closing date that reads the same in both orders.
6. **Printed pages the engine never sees** (`_numbering_complete(after=...)`): pages missing from the printed
   numbering only after the page where the movement table printed its own end (year-to-date heading, column
   total or closing line after its last movement) do not hold the period; the proof records
   `pages_unread_after_table`. (Synchrony prints "page 3 of 3" on a last physical page that holds only its
   footer and has no stored table, so the engine saw "page 1 of 3" and "page 2 of 3" only.)
7. **Unlocated rows** (`_unlocated_matters`): hold the reading (no_geometry) only when one of their lines could be
   a movement (date + amount), an undated card charge, or an opening/closing/total/section-total control.
8. **Holder**: a postal line can be the address block's own cell (another box shares its stored row); such a
   block must reduce to name + house-number/PO-box lines + postal line, 3-4 lines, below any paragraph gap
   (`_spaced_block`, `_street_lines`). A payment stub printed below the first page's movements gives the holder
   only when the same name is printed as a whole cell above the movements (`_stub_holder`).

## Measured (counts)

### Synchrony (truth-mini-v17: 16 documents, 16 verified periods, 47 rows)

| | blind (t-visual-v17, deployed code) | **r6-synchrony** |
|---|---|---|
| Ready without any edit | 0/16 | **16/16** |
| Wrong admissions / critical-field errors | 0 / 0 | **0 / 0** (47 rows saved from 16 periods) |
| Rows equal to truth (date, amount, direction) | 0/47 read | **47/47**; inverted 0 |
| Balances equal to truth | 0/16 read | **16/16** |
| Compared without disagreement | 0/16 | **16/16** (mini and whole set) |
| Investigator actions (single / grouped) | 190 / 130 | **0 / 0** |
| Engine-served / library-served | 0 / 0 | **16 / 0** |
| Generic-only (family readers skipped, profiles applied) | 0/16 | **16/16**, 0 wrong |
| Plain engine without the profile | 0/16 | 2/16 (closing day <= 12 in every cycle: only the two dates that read the same both ways) |

- Stored periods: start `derived` / end `printed` / balanced 16/16. Start agreed with the previous statement in
  the case 15, first cycle by the printed day count alone 1.
- Rules each period relies on: printed-totals proof 16 (no running balance printed), pages unread after the
  table end 15, unlocated table ignored 2, holder from the address block 11 / from the stub below the movements
  5; 186 rows read from split lines.
- Neil's ruling 2 (late-posted charges) on this family: truth rows dated before the derived cycle start 0, after
  the closing date 0 (47 inside). Nothing for the rule to act on (as t-visual-v17 found).

### Whole real truth set (bench/r6s-full; frozen eea33ee0; corpus snapshot bench/r6s-corpus = the same 583 documents / 1,424 periods as bench/wave5; `--readings` bench/wave5)

| | bench/wave5 (ef0877d6) | **r6s-full (eea33ee0)** |
|---|---|---|
| Ready without any edit | 1,118 / 1,253 (89.2%) | **1,134 / 1,253 (90.5%)** |
| Recoverable ready | 1,118 / 1,249 | **1,134 / 1,249 (90.8%)** |
| Wrongly admitted | 0 | **0** |
| Critical-field errors in saved rows | 0 (17,085 rows / 1,128 periods) | **0 (17,132 rows / 1,144 periods)** |
| Must-hold kept out / exact copies held | 4/4, 148/151 | 4/4, 148/151 |
| Previously ready periods lost | — | **0** (gained 16, all synchrony-card) |
| Engine-served / library-served ready | 92 / 1,026 | **108 / 1,026** |
| Batch items matched to no truth period | 18 (0 offered) | 18 (0 offered) |
| Valid-looking wrong values proposed | 68, 0 in ready periods | 58, 0 in ready periods (*) |
| Investigator actions, 583 statements (single / grouped) | 3,785 / 3,638 | **3,593 / 3,506** (616 / 601 per 100) |
| Compared without any disagreement (periods + items) | 1,263 / 1,442 | **1,279 / 1,442** |

(*) The 10 fewer are in one held Andrews period and one held Monex period whose documents this branch reads
identically (engine survey); the harness paired them with a different batch item of the same file. A scoring
pairing artefact, not attributable.

Every other family's ready count is unchanged; Synchrony is the only family whose ready set moved. The run's
exit status was not captured (a duplicate launch collided with the running one's log file; the duplicate failed
at table creation and changed nothing); its exit criterion, wrongly admitted periods, is 0.

### New row splitting / rules on every other family (engine survey, all 583 documents, wave-5 readings, base fb8abfdf vs eea33ee0)

- Engine-proved statements lost: **0** in every family. Newly proved: bbva 1, capital-one 4, monex 1 (plus
  synchrony 16). In the real run none of these changes what is served or ready: bbva and monex gain an
  engine/library agreement; the Capital One library reader still reconciles those periods (my cached survey
  sources lack the Capital One layout context, so the survey alone overstated a replacement).
- Identity of proved statements: unchanged outside Synchrony. Held statements: rows now prefilled on 3 (citi 2,
  merrick 1; library-served documents), hold reason changed on 9 (credit-one).
- Bonus periods newly proved elsewhere: none ready that were not already ready.

### Synthetic (bench-runs/r6-synchrony-eea33ee0, frozen eea33ee0)

105/125, recoverable 105/108, 0 wrong, 0 critical (354 rows), holds 10/10, copies 1/1, 0 valid-looking wrong
values, **BENCH_EXIT=0** (rescore of the same run).

## Tests actually run

- New: 13 engine tests (`BoxedCardTests`; 11 fail on fb8abfdf, 2 are guards), 5 closing-only tests
  (`DayCountPeriodTests`). Synthetic fixtures only.
- Engine / closing-only / card summary / import batches / review arithmetic / admission / statement import /
  proposal / review checks / exports / bulk details / real compare: **475 OK**.
- Full financial suite on eea33ee0: **Ran 6,107; failures 2, errors 1, skipped 20.** The 2 failures are the
  known `unassigned_statement` pair (fail identically on fb8abfdf); the error is a subprocess timeout in
  `public_timestamp_opt_in` under host load (passes alone, 1 test OK).
- Frontend not touched.

## Live ledger (read-only question; nothing read or written live in this unit)

The investigator's two hand-entered Synchrony periods (d43853a185720#1, d7f1c8c31414c#1; every direction inverted
live) are both in the mini corpus and the whole set: this code reads **both ready and equal to truth**, every
direction right. Correcting the live rows is a re-read / re-entry: a live write, not done here.

## Decisions taken (each reversible in one place)

1. One-cell movement tables split by printed line. Reverse: the first branch of `_split_row`.
2. Boxes on one stored row read box by box; payment box never a control. Reverse: second branch of `_split_row`
   / `PAYMENT_BOX_HEADINGS`.
3. Net summary lines and NEW PURCHASES. Reverse: `LIABILITY_NET_COMPONENTS`, the entry in
   `LIABILITY_DEBIT_COMPONENTS`.
4. Section totals as controls (proof + review scope). Reverse: `SECTION_TOTALS` (empty it).
5. Closing-only start derived from the printed days, never printed, agreeing with the previous statement where
   present. Reverse: `_closing_only_period` (drop the call in `_derived_period`); case check in
   `closing_only_period._day_count_dates`.
6. Printed pages unread only after the table's printed end do not hold the period (15 Synchrony periods rely on
   it). Reverse: the `after=` branch in `_read_section`.
7. Unlocated rows matter only when they could be a movement or a control. Reverse: `_unlocated_matters` -> True.
8. Holder from an own-cell postal line (address-shaped) and from the payment stub. Reverse: `own_cell` branch in
   `_address_tops`; `_stub_holder`.
9. `synchrony-card` profile: institution, USD, amounts owed, month-first dates. Reverse: remove the entry.

## Open / next unit

- Pre-existing inconsistency (not changed): r5's Mexican cut-date + day-count period (`_derived_period`) is stored
  with a PRINTED start; this unit's English closing-only rule stores DERIVED. Aligning the Mexican rule changes
  the stored start provenance of ready periods (not their dates); a separate unit with its own whole-set check.
- Capital One holder: the address block on those statements reads correctly only through a wider rule I tried
  and withdrew (it also produced wrong holders on Credit One help text); library-served, so nothing lost.
- The shared `/mnt/owl-data/fin-real/compare/` holds this branch's mini-run comparison for the 16 Synchrony
  documents (16 without disagreement); the integration run rewrites it.
- Next family by held periods: andrews 35 recoverable held, santander 24, merrick 19, bbva 16.

## Decisions needed from Neil

1. Live: re-read (or re-enter) the investigator's two hand-entered Synchrony periods once this is deployed, and
   merge the card's two live accounts; this code reads both equal to truth. A live write, interactive session.
2. Ratify decision 6: a period proves although the printed page numbering shows pages the engine never saw, when
   those pages come after the movement table's own printed end. Recommended: keep (the table's printed end means
   no movement can follow it; must-hold 4/4 and 0 wrong on the whole set). Without it Synchrony is 1/16.
