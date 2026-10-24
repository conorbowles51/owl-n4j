# Loupe financial: state assessment and usability benchmark

Date: 2026-10-24. Live code at time of writing: `68d95b20` (deployed 2026-10-24 07:29 UTC).
All live figures come from read-only queries run 2026-10-24 between 20:30 and 20:50 UTC (method in Appendix B).

## Bottom line

After months of work, the financial module is safe but not yet useful at scale. Across all six live cases, 47% of statements reached the ledger with no human action, 39% went in through imports Alex ran, and 14% (326 statements) are still waiting. BNB2 is 62% automatic with 133 waiting; Erica Hopper is 30% automatic with 167 still outstanding and has had almost no attention this week. The 95.6% figure that has been the headline is a fresh-read bench on documents with verified answers. It does not describe Alex's queue, mainly because live statements are not re-read when readers improve and because anything she has touched is frozen. The part that works is the safety model: 0 wrong admissions on every scored run, copies set aside rather than counted, and a boxed source location for 99.9% of the 29,884 live transactions. No competitor researched documents any of these, and none claims coverage of the Mexican banks Loupe reads. The part that does not work is how coverage is built and how the residue is handled. Coverage comes one layout at a time (an unseen layout starts near zero), the yield per round is falling (about 19 of 149 held statements in the last full round), built fixes sit on unmerged branches (22 of them, including a fix for a live double count), and fixing a held statement is a slow, mouse-driven form where most of the work is typing rows. Competitors have weaker safety but a much faster residue: exceptions-only review that points at the broken row, a case-wide coverage grid, keyboard flow, and a one-button exhibit. The recommendation is to keep the arithmetic gate and stop treating per-bank readers as the main route to coverage. Ship what is built (automatic re-reading, carry-edits, row proposals), make a vision reader behind the same gate the first pass for anything a proven reader holds, report the live "needs Alex" count per case as the only headline, and rebuild the held-statement screen and the case status around her task. Without the vision step, BNB2 is likely to stall at about 80-100 waiting. With it, getting both large cases under about 30 each is plausible in 2-4 weeks. These are estimates, not measurements.

## Contents

- Part 1. Where the financial work actually is
  - 1.1 What is live, built, being built, planned
  - 1.2 Coverage measured on the live system, all cases
  - 1.3 Live versus bench: why the numbers disagree
  - 1.4 Coverage trend
  - 1.5 Why the same issues keep coming back (root causes, ranked)
  - 1.6 Open decisions waiting on Neil
  - 1.7 Realistic outlook
- Part 2. Usability audit of Loupe's financial UI
- Part 3. Competitive usability benchmark
- Part 4. Prioritised improvement list
- Appendix A. Sources. Appendix B. Queries run. Appendix C. Screenshots. Appendix D. Method notes.

---

# Part 1. Where the financial work actually is

## 1.1 What is live, built, being built, planned

| State | What | Evidence |
|---|---|---|
| **Live** | `68d95b20`, deployed 2026-10-24 07:29 UTC. Contains: BNB2 queue units A/A2/B/C (Santander online queries, brokerage currency from the account, overlap trimming, details carry), copies set-aside and fund-statement rule, Santander sub-accounts, currency/bank autofill and per-account grouped confirm, the "Needs Alex / Loupe is handling" queue split with numbered steps. Earlier live: wave 13 (`6f626b2a`, 2026-10-22 18:52), automatic save of ready statements (since 2026-10-14). | STATUS-FOR-NEIL.md; ALEX-QUEUE-WORK.md 07:29-07:35 lines; first `auto-save@system.local` ingestion run 2026-10-14 18:58 UTC (live DB) |
| **Built, not deployed** | `fin/rd-release1` `78139cc5` (20 commits ahead of live): reader-gap round (BBVA, Santander, Monex, Kapital, Intercam, Scotiabank), automatic re-preparation of held statements after a reader change, missing-pages gate, autofill re-apply. Simulated on BNB2: 18 of 134 waiting become ready; 11 fund statements leave as "not a payment statement". Independent review running; truth-set comparison running on a swapping host. | STATUS-FOR-NEIL.md; `git log HEAD..fin/rd-release1` |
| **Built, not deployed, and not on the release path** | Wave 15 on `fin/release-1` (18 commits ahead of live, 2026-10-23): `r15-hold-gaps` (missing-pages hold for every reader; a copy read into another ledger account set aside), `r15-batch-work` (row proposals confirmed per page, switch default off), `r15-andrews-structure`. The missing-pages gate was rebuilt from scratch on 2026-10-24 as `fin/rd-pagegate` instead of landing the 2026-10-23 version. | `git log HEAD..fin/release-1`, `HEAD..fin/r15-hold-gaps` |
| **Being built** | `fin/rd-creditline` `9cc3f97e` done, 0 of 8 held statements prove (blocked on a date-column decision); `fin/rd-carryedits` (carry Alex's edits onto a fresh reading: 83 BNB2 originals / 93 items protected today because she worked on them); shared-pages two-account fix. | ALEX-QUEUE-WORK.md 20:05 lines |
| **Planned, not started** | Vision fallback reader (OpenAI `gpt-4o`, held statements only, accepted only when arithmetic proves). Approved 2026-10-24 17:01/17:35, queued last. | VISION-APPROVED; rd-finish.md item 4 |
| **Planned months ago, still open** | Ledger to graph projection (`fin/u2-projection`, 2026-10-02: 0 FinancialTransaction nodes in Neo4j). Error register U01-U09 (2026-09-27): consistent counts across screens (U01), distinguish documents / periods / payments (U02). See 1.5 and Part 2 for which of these still reproduce. | memory project_loupe_financial_automation.md; error-register-2026-09-27.md |

Scale of the effort: 725 commits touching `backend/services/financial` or `frontend_v2/src/features/financial` since 2026-08-01; the financial backend is 254 files / 87,902 lines; the financial frontend is 214 `.tsx` files / about 90,000 lines; 291 financial test files; 123 `fin/*` branches, 22 of them not merged into the live branch.

## 1.2 Coverage measured on the live system, all cases

Six cases hold financial evidence. "Saved automatically" = the ledger period was written by the system's auto-save with no click. "Saved by Alex" = written by an import Alex started (this includes one-click imports of statements that needed no edit; auto-save did not exist before 2026-10-14). "Outstanding" = everything in the queue that is not saved and not a copy: waiting for Alex, waiting for a reader fix, ready but unsaved, couldn't read, unexplained.

| Case (short name) | Current ledger periods | Saved automatically | Saved by Alex | Waiting for Alex | Waiting for reader fix | Ready, not saved | Couldn't read | Unexplained | Copies set aside | Admitted transactions |
|---|---|---|---|---|---|---|---|---|---|---|
| BNB2 (Eagle & Serpent) | 1,187 | 838 | 349 | 133 | 0 | 8 | 5 (4 + 1 file) | 11 | 93 (+1 file) | 23,650 |
| Erica Hopper (OPDMD62) | 703 | 260 | 443 | 137 | 14 | 1 | 15 (13 + 2 files) | 0 | 172 | 4,285 |
| monday finance | 58 | 0 | 58 | 0 | 0 | 0 | 0 | 0 | 0 | 960 |
| finance sunday | 53 | 0 | 53 | 0 | 0 | 0 | 0 | 0 | 0 | 672 |
| neil finance | 7 | 0 | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 317 |
| Pop & Locke (SB4) | 0 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| **All cases** | **2,008** | **1,098** | **910** | **272** | **14** | **9** | **20** | **11** | **265** | **29,884** |

Headline, all cases, statements that are not copies (2,008 saved + 326 outstanding = 2,334):

| | Statements | Share |
|---|---|---|
| Reached the ledger with no human action | 1,098 | **47%** |
| Reached the ledger through an import Alex ran | 910 | 39% |
| Still outstanding (needs Alex, a reader fix, or is unreadable) | 326 | 14% |
| **Needed or still needs Alex** | **1,236** | **53%** |

Per case: BNB2 62% automatic, 26% by Alex, 12% outstanding. Erica Hopper 30% automatic, 51% by Alex, 19% outstanding.

Two caveats that cut in opposite directions:
- The "by Alex" figure overstates current manual need: 805 of her imports happened before auto-save existed, and some of those statements would save automatically today. No fresh live measurement of "what share would today's code save untouched" exists. The nearest is the census of all live periods on cached readings (census-r5, wave-5 engine, about 2026-10-13): **1,165 ready with zero edits out of 3,154 raw periods (37%)**; BNB2 531 / 1,397, Erica Hopper 333 / 1,189.
- The outstanding figure understates the work behind it: the BNB2 queue alone groups 133 waiting statements into 8 reasons, and 93 items are frozen because Alex already touched them (carry-edits not built).

Why statements wait, live, by reason (queue issue counts):

| Reason | BNB2 | Erica Hopper | What it means |
|---|---|---|---|
| Balances (payments read, opening/closing not, or they do not add up) | 46 | 89 | The arithmetic check cannot be run or fails |
| Reading (rows unreadable, OCR damage) | 34 | 27 | Nothing reliable read on one or more pages |
| Currency to confirm | 25 | 2 | Loupe proposes the case's usual currency; by rule a person confirms |
| Bank (institution) | 10 | 2 | Bank name not read |
| No activity | 6 | 0 | A quiet period the system cannot prove empty |
| Holder | 5 | 1 | Account holder not read |
| Account number | 5 | 1 | Account not read |
| Earlier saved review work | 2 | 1 | Alex's own work on an older reading |
| Principal-only credit line | 0 | 12 | Loan statement printing only a principal balance |
| Assignment | 0 | 2 | Which account a section belongs to |

By bank, live ledger, the two large cases (current periods; automatic / by Alex):

| Bank | Periods | Automatic | By Alex | Automatic share |
|---|---|---|---|---|
| BBVA (BNB2) | 496 | 268 | 228 | 54% |
| Accounts named "Banco ..." (BNB2) | 265 | 264 | 1 | 100% |
| Intercam (BNB2) | 134 | 115 | 19 | 86% |
| Monex (BNB2) | 120 | 78 | 42 | 65% |
| Santander (BNB2) | 112 | 75 | 37 | 67% |
| Kapital (BNB2) | 53 | 33 | 20 | 62% |
| Scotiabank (BNB2) | 5 | 5 | 0 | 100% |
| Navy Federal (Erica Hopper) | 205 | 152 | 53 | 74% |
| Andrews (Erica Hopper) | 151 | 9 | 142 | 6% |
| Capital One (Erica Hopper) | 130 | 0 | 130 | 0% |
| M&T (Erica Hopper) | 86 | 86 | 0 | 100% |
| Citibank (Erica Hopper) | 49 | 0 | 49 | 0% |
| Merrick (Erica Hopper) | 42 | 0 | 42 | 0% |
| Credit One (Erica Hopper) | 25 | 0 | 25 | 0% |
| Synchrony (Erica Hopper) | 15 | 13 | 2 | 87% |

The 0% rows are families Alex imported before auto-save existed; the bench now scores Capital One 127/130, Citi 49/49, Merrick 35/42, Credit One 51/53 (real/STATE.md family table), but those live statements have not been re-read since, so the live product has never demonstrated those numbers.

Other live facts relevant to trust:
- 106 current saved periods (65 BNB2, 41 Erica Hopper) have no period start date; 6 saved periods are "unbalanced" and 146 have reconciliation "unavailable" (no printed opening, or not computable). These periods are in totals and flows.
- 11 saved BNB2 BBVA statements are missing their printed page 1 (cover with opening balance), found by the 2026-10-24 audit; 1 saved statement may carry the wrong currency; 2 periods were admitted twice into different ledger accounts (real/STATE.md, open decision 3; the fix is on unmerged `fin/r15-hold-gaps`).
- The queue headline "Imported 2,157 statements" for BNB2 does not match the ledger: there are 1,187 current BNB2 statement periods (1,282 distinct imported statement keys across 1,406 files). The queue counts batch entries, including the same statement saved through another batch. An analyst reading the screen cannot reconcile it with the ledger.
- Alex's last import action was 2026-10-22. Her import activity by week: 72, 526, 178, 26, 302, 2 (weeks of 14 Sep to 19 Oct).

## 1.3 Live versus bench: why the numbers disagree

The bench of record says **1,664 of 1,740 verified real periods (95.6%) are ready with no edit, 0 wrong** (wave 14). Live BNB2 says 62% automatic and 133 waiting. The gap is real and has identifiable causes:

| Cause | Evidence | Size |
|---|---|---|
| **Stale readings.** Live statements were read by older reader versions and are not re-read when readers improve. Automatic re-preparation of held items is built (`held_reprepare`, rg-refresh) but not live. | 99 of 155 BNB2 waiting (2026-10-23) were in the truth set and the bench saved 50 of them (ALEX-QUEUE-WORK.md "KEY FINDING"); 27 autofilled statements made 0 ready because their stored keys predated the deployed reader. | Largest single cause |
| **Alex's own work freezes statements.** Any statement she touched is protected from re-reading until carry-edits exists. | 83 BNB2 originals / 93 items protected (rg-refresh, 15:04) | ~90 items |
| **The truth set excludes the hardest documents.** Truth covers what could be transcribed and verified; unverified and unscored documents are outside the 95.6%. | 33 unverified periods, 18 unscored documents, 3 incomplete (STATE.md truth coverage); truth = 1,740 periods vs 3,154 raw live periods in the census | Truth covers ~55% of live periods |
| **The bench measures product readiness, not Alex's whole queue.** Copies, her saved-review conflicts, cross-batch interactions, removed files and live ordering effects do not exist in the bench. | Live crash on duplicate recovery items via two batch files (fixed `1dd1091f`); stale "ready" display; 211 removed files in BNB2 | Unquantified |
| **Readiness depends on host load.** | "readiness depends on host load and fresh reads are not guaranteed identical across runs. The ready count is a floor." (STATE.md) | Unquantified |
| **Auto-save is recent.** | First auto-save 2026-10-14; 805 of Alex's 910 imports predate it | Historical |

Conclusion: the 95.6% is a credible measure of what the current readers do on a fresh read of documents that have verified truth. It is not a measure of Alex's experience and should stop being reported as the headline. The measure Neil set on 2026-10-23 ("the live waiting count falls with 0 wrong") is the right one.

## 1.4 Coverage trend

Bench of record (fresh read, verified real truth; the denominator grows as truth grows):

| Date | Wave | Ready w/o edits | % | Synthetic |
|---|---|---|---|---|
| 2026-10-02 | baseline, synthetic v1 / v4 | 12/26 ; 61/124 | 46% ; 49% | — |
| 2026-10-05 | real wave 0 | 484 / 761 | 63.6% | 102/124 |
| 2026-10-06 | 1 | 800 / 1,035 | 77.3% | 105/125 |
| 2026-10-08 | 3 | 977 / 1,191 | 82.0% | 105/125 |
| 2026-10-10 | 4 (deployed `a15230a0`) | 1,034 / 1,237 | 83.6% | 105/125 |
| 2026-10-13 | 5 | 1,118 / 1,253 | 89.2% | 105/125 |
| 2026-10-16 | 7 | 1,147 / 1,343 | 85.4% | 105/125 |
| 2026-10-17 | 8 | 1,252 / 1,397 | 89.6% | 105/125 |
| 2026-10-18 | 9 | 1,315 / 1,436 | 91.6% | 108/125 |
| 2026-10-19 | 10 | 1,351 / 1,462 | 92.4% | 108/125 |
| 2026-10-21 | 12 | 1,404 / 1,524 | 92.1% | 108/125 |
| 2026-10-22 | 13 (deployed `6f626b2a`) | 1,645 / 1,729 | 95.1% | 108/125 |
| 2026-10-22 | 14 (not deployed as a unit) | 1,664 / 1,740 | 95.6% | 108/125 |

Generic engine alone (no bank-specific reader): wave 5 717/1,237 (58%); wave 14 1,259/1,740 (72%).

Live (BNB2 queue as Alex sees it):

| Time (UTC) | Imported (queue figure) | Waiting for Alex | Couldn't read | Copies | Source |
|---|---|---|---|---|---|
| 2026-10-02 | Erica Hopper batch: 53 of 244 ready (22%) | 191 blocked | | | memory file |
| 2026-10-15 17:40 | 1,532 | 346 | 329 (207 of them removed files) | 159 | r7-alex-queue explainer |
| 2026-10-23 23:05 | 2,014 | 155 | | 105 | ALEX-QUEUE-WORK baseline |
| 2026-10-24 07:37 | 2,070 | 74 (+127 rechecking) | 4 | 97 | ALEX-QUEUE-WORK |
| 2026-10-24 12:56 | 2,155 | 134 | 4 | 93 | ALEX-QUEUE-WORK |
| 2026-10-24 20:35 | 2,157 | 133 | 5 | 93 | this assessment |

Reading the trend honestly:
- **The bench curve is flattening.** +316 ready periods in the first week of real waves, single digits per unit in the last waves ("fixes now unlock single digits per wave", STATE.md decision 5). Much of the late rise came from adding new truth (denominator) and families where a reader was then written, not from general capability.
- **The live queue has moved, but slowly at the tail.** BNB2 waiting went 346 → 155 in eight days (mostly the big re-read and auto-save), then 155 → 133 in the last 21 hours of intense multi-agent work. The release on the bench (`rd-release1`) is simulated to take 18 more off (→ about 115).
- **Reader-gap round yield (2026-10-24, four parallel units, one day):** of 149 held BNB2 statements, BBVA +1 of 46, Santander 4 of 31, others 11 of 32, unidentified +3 of 40 (plus 11 fund statements reclassified): about 19 of 149 (13%).
- **Extrapolation.** At the current per-round yield (roughly 15-20 statements per release, with each round's yield falling), BNB2 reaches about 80-100 waiting after two more rounds and then stalls on a hard core: OCR-damaged scans (18 BBVA), missing pages (10), credit lines (8), statements Alex has already touched (~90 protected items overlapping the above), and currency confirmations that are kept manual by rule (16-25). Erica Hopper (137 waiting + 14 reader fix + 15 unreadable) has had almost no attention in the last week and will not move without it. A per-bank reader programme does not reach "Alex unblocked" on either case on any timeline that can be stated with confidence.

## 1.5 Why the same issues keep coming back (root causes, ranked by impact)

**1. Coverage is built one layout at a time, and a new layout starts near zero.** (Highest impact.)
- 12 bank-specific import modules (`statement_import_bbva`, `_santander`, `_santander_query`, `_monex`, `_kapital`, `_scotiabank`, `_andrews`, `_merrick`, `_citi`, `_credit_one`, plus period pinning and sub-account rules) on top of a general engine with per-bank profiles.
- Blind arrivals before their reader existed: M&T 0/41 and 0/49 ready (t-visual-v15, v16), Synchrony 0/16 (r6-synchrony); Andrews, Credit One and Merrick score 0 under the general engine alone (library-only families: 255 + 51 + 35 periods).
- Each live fix is a rule for one printed quirk ("rule apostrophe, spaced cover account, quiet cover closing", "date underline-mark rule", "Scotiabank footnote-mark switch"). There are 21 `LOUPE_FINANCIAL_*` switches in `backend/services` on the live branch, more on unmerged branches.
- Consequence: every new production, bank or scan quality re-opens the problem. The approach is accurate where it is finished and brittle everywhere else. This is the structural reason the issue "keeps coming back".

**2. The safety rule is right; the path for what it holds is missing.**
- The fail-closed rule (save only when opening + rows = closing and identity checks pass) has delivered **0 wrong admissions on the scored real set in every wave**. That is a genuine asset and should be kept.
- But nothing efficient happens to what it holds. 58% of the residual human actions on the bench are rows to type after a reading failure (616 of 1,058, STATE.md), and the one unit aimed at that (`r15-batch-work`, page row proposals confirmed per page) was built on 2026-10-23 behind a switch that defaults off and never merged. Alex's review of a held statement is still per statement, per field.
- Some holds are policy, not capability: 25 BNB2 currency confirmations where the account's other statements make the answer obvious stay manual by rule. That rule is defensible; it should be one bulk confirm, which is now built (grouped confirm, live, 5 groups showing).

**3. The bench drove the work, and the bench is not the queue.** See 1.3. For three weeks the headline was the bench percentage; the live queue only became the success measure on 2026-10-23. The stale-reading problem (the largest live cause) is invisible to a fresh-read bench by construction.

**4. Work forks faster than it lands.** 123 `fin/*` branches; 22 unmerged. Wave 15 (three units including the missing-pages gate and the cross-account copy fix for a live double admission) was built on 2026-10-23 and left on `fin/release-1`; the missing-pages gate was rebuilt the next day as `fin/rd-pagegate`. Several coordinator sessions (interactive, two takeovers, relays between them) each hold part of the state. Every release carries merge-reconciliation work.

**5. Releases are slow to reach Alex.** Deploys defer while a recovery or ingestion runs (exit 75): `69019593` took 16 attempts. Whole-set benches take about 9 hours; on 2026-10-24 they were SIGSTOPped, crashed on `database is locked` and were killed for memory. The host ran at load ~180 with swap full. The same pattern was already on the 2026-09-27 error register (E07: "Code-only fixes were pushed, but automatic deployment deferred for active ingestion").

**6. The UI exposes the pipeline's states rather than the analyst's task.** Detailed in Part 2. The 2026-09-27 register asked for consistent counts across screens (U01) and for documents, periods and payments to be distinguished (U02). Today the queue still reports "Imported 2,157" against 1,187 periods in the ledger, and still shows states such as "Waiting for a reader fix", "Loupe is handling", "rechecking", "unexplained", "Left out by you".

**7. Decisions queue on one person.** STATE.md carries 15 open decisions; STATUS-FOR-NEIL carries 3 more; several (live double admission repair, 396 live batch items, catalogue backfill, re-reading 4 live periods that disagree with print) are live-data repairs that have waited since wave 10-13.

**8. Nondeterminism in reading.** Readiness varies with host load (OCR timeouts mark pages unread). A safety system whose output depends on how busy the machine is cannot give Alex a stable queue.

## 1.6 Open decisions waiting on Neil (consolidated, each with a recommendation)

| # | Decision | Recommendation |
|---|---|---|
| 1 | 11 saved BNB2 BBVA statements missing printed page 1 | Keep saved; mark "cover page missing" with the page list so Alex can find the full statement. Do not un-save. |
| 2 | One saved statement possibly in the wrong currency (MXN on a USD ledger) | Put it in Alex's queue as a single check with both readings shown. |
| 3 | Live double admission: 2 BBVA periods saved into two ledger accounts (58 + 57 payments counted twice) | Repair now (page-identity backfill, set aside across accounts); merge `r15-hold-gaps` item 2 so it cannot recur. Every day it waits, BNB2 totals are wrong. |
| 4 | Live rows/holders that disagree with print (4 re-reads, 2 hand-entered Synchrony periods, 3 Kapital address-as-holder) | Re-read through the normal recovery path. |
| 5 | Credit-line layout date of record (`rd-creditline`, 0 of 8 prove without it) | Application date, own switch. |
| 6 | Wave 15 branch (`fin/release-1`): land or abandon | Land `r15-hold-gaps` item 2 and `r15-batch-work` (default on, behind a switch) in the next release; delete what `rd-pagegate` supersedes. Stop parallel rebuilds. |
| 7 | Vision fallback: order and scope | Move it up: build it as the extraction path for held statements now, not after credit lines and carry-edits (see Part 3.4). |
| 8 | Headline metric | Report only live "statements needing Alex" per case plus 0-wrong; demote the bench percentage to a regression gate. |
| 9 | Erica Hopper | Give it the same queue treatment as BNB2; it has more outstanding (167) than BNB2 (157). |
| 10 | 396 live batch items shown as saved through another upload; catalogue backfill | Approve both when no import is running. |

## 1.7 Realistic outlook

What "Alex unblocked" should mean, measurable: on each live case, the statements needing her are few enough to clear in one sitting (under ~30), each one shows the page and the exact thing to do, and nothing saved is wrong.

| Path | What it takes | Honest range |
|---|---|---|
| Continue reader-by-reader | Ship `rd-release1`, carry-edits, credit lines, then more reader rounds | BNB2 to ~80-100 waiting in 1-2 weeks; plateaus there. Erica Hopper unchanged unless worked. New productions restart the cycle. |
| Reader + automatic re-read + carry-edits | Same plus re-reading every live statement with the current code | BNB2 could plausibly fall into the 50-80 range (the 93 protected items are the lever); 1-2 weeks if releases land. |
| Vision/LLM extraction for held statements, with the existing arithmetic check as the gate, plus a side-by-side review screen | 2-4 weeks to build and prove on truth, then live | The only path with a credible chance of taking BNB2 and Erica Hopper to under ~30 each. Risks in Part 3.4. |

None of these ranges are measurements. They are the best available estimates from the per-round yields above, and should be replaced by the live count after each release.

---

# Part 2. Usability audit of Loupe's financial UI

Method: read from source (`frontend_v2/src/features/financial`, live branch `68d95b20`), the in-app user guide (`public/docs/financial-guide`) and live read-only data. **No live screenshots were taken**: no test login exists in the repository or docs, and forging a session token against the live system was not acceptable. The guide's own 47 screenshots (synthetic data, `public/docs/financial-guide/images/`) are the visual reference. Click counts below are counted from the code and guide; they have not been measured on a live session and are marked (from code).

## 2.1 Size and shape of the surface

| Fact | Value | Why it matters |
|---|---|---|
| Financial views (tabs) | 16 (`financialMainViews`): 7 primary, 5 under "More financial tools > Further analysis", 4 under "Import and review history" | A new user faces seven tabs plus a menu of nine more |
| Components on the "Statements & accounts" tab | Up to 9 stacked, some conditional: case review status, account ownership review, account type review, register checks, review queue, statement register, statement import panel, checks, coverage | The working screen for Alex's main job is a long scroll of independent panels |
| Statement review screen | `StatementImportPanel.tsx` 5,069 lines, 58 `useState` hooks | The screen where a held statement is fixed is the most complex component in the app |
| Keyboard handling | 5 components in the whole feature have any key handler; the statement review screen has one | Review is mouse-driven, field by field |
| User guide | 2,067 lines, 35,020 words, 158 headings; plus a 716-line, 12,554-word team testing checklist | Needing 35,000 words to explain the feature is itself the finding |
| Upload path in the guide | "Upload PDFs ... up to 20 at once"; folder-scale loads go through Evidence selection and batches | Two loading paths with different behaviour |

## 2.2 The analyst's core jobs, walked through

| Job | How it works today (from code and guide) | Steps / screens (from code) | Friction found |
|---|---|---|---|
| **(a) Load a folder of statements** | Select files in Evidence (or Upload PDFs, max 20), choose Financial; reading starts by itself; a batch is created or continued (`BatchStartChoice`: "continue" is the default) | 3-5 clicks; then wait (hours for a production: BNB2's 1,452-file read ran most of a day on 2026-10-15) | No estimate of finish time. Copies announced up front (good). Removed files were swept back into selections (207 on 2026-10-15) and still count: BNB2 shows "Files removed from Financial 211". |
| **(b) See what got read and what didn't, and why** | Review queue status line: "Imported 2157 statements · Waiting for you 133 · Ready to import 8 · Copies set aside 93 · Couldn't read 5 · Left out by you 1 · Files removed from Financial 211"; "Needs <name>" vs "Loupe is handling" split; issue filter | 1 screen | **The headline count is wrong for the purpose**: 2,157 "imported" against 1,187 statement periods actually in the BNB2 ledger (batch entries, not statements). Seven different states in one line. "Waiting for a reader fix" (14 in Erica Hopper) states that the software must change before these statements can move, and gives no date. No per-account view of what is covered and what is missing on this screen. |
| **(c) Fix/complete a held statement** | Queue item: plain title, numbered steps with page, one action ("Open the PDF" or answer inline); opens the statement review panel; side-by-side "Original statement" with the value boxed when a row is focused; edit import values, add missed transaction, clear "Use" | 1 queue click + 3-8 per fix; a page of missed rows means typing each row (date, description, amount, direction, reason) | 58% of residual bench work is typing rows (616 of 1,058 actions). The row-proposal tool (`r15-batch-work`) is built, switched off, unmerged. No "next problem" key flow. The issue label "balance" covers two different problems (both balances read but amounts unreadable vs balances missing): 43 of 80 "balance" holds were really unreadable payment amounts (autofill unit, 2026-10-24). |
| **(d) Find duplicates/copies** | Copies set aside automatically and linked; "Copies set aside" list with "a possible copy says so and asks you to compare it"; duplicate register and decision form | 1-3 | Works and is a strength. Gap: a copy saved into a second ledger account was not caught live (2 BNB2 periods counted twice; fix unmerged). |
| **(e) See an account's full history and balances** | "Account balances and activity" (`AccountHistory`): per statement period, opening/closing, "Start missing", "End missing", "Confirmed quiet period", "Needs review"; statement coverage check per account with a dates-included/left-out timeline | 2-4 | Coverage is per account and has to be opened account by account ("Review an individual account to check an earlier or later date range"). There is no one-screen account-by-month grid across the case of the kind Valid8 has. 106 saved periods have no start date and drop out of date-based views. |
| **(f) Follow money between accounts/people** | Follow money, People & businesses, Compare transfers, Trace funds (one account / between accounts), Payment graph, Payments and case events timeline | 2+; five overlapping tools | Five entry points to adjacent questions; the analyst has to know which tool answers which question. Ledger-to-graph projection is merged (`fin/u2-projection` is an ancestor of live). |
| **(g) Search/filter transactions** | Transactions: search, filters, charts that filter on click, totals describing exactly the filtered rows, corrected values used in totals | 1-3 | Good. Totals only use corrected values (a standing design rule), which is correct and unusual. |
| **(h) Flag/annotate and export for a report / court exhibit** | Select payments, save a finding with title and explanation (payments and source references attached); Findings > Include in report > Build report (10 steps in the guide); CSV and ZIP downloads; export manifest separates generation time so identical ledgers export identical bytes | 10+ | Thorough, but long. No single "exhibit for this account" button producing an indexed PDF with a page citation per transaction and file hashes, which Valid8 and Docuritas present as their main output. |
| **(i) Trace a transaction back to the source page** | Transaction detail panel shows the source page with the value boxed | 1 | **Best in class among the tools researched.** 29,867 of 29,884 live admitted transactions (99.9%) carry a page plus a rectangle on that page (live query). No competitor researched documents per-transaction boxed source on screen; Valid8 opens the whole PDF from a File column. |

## 2.3 Nielsen's 10 heuristics, scored 1-5

| # | Heuristic | Score | Evidence |
|---|---|---|---|
| 1 | Visibility of system status | 2 | Reading progress ("Reading 1,232 of 1,452 files") exists. But the queue's "Imported 2,157" does not match the 1,187-period ledger; a stale "ready" display showed 5 already-saved items as ready (2026-10-23); "rechecking" and "Loupe is handling" hide what is happening and for how long; reader fixes arrive only by deploy, so "Waiting for a reader fix" has no horizon. |
| 2 | Match between system and the real world | 3 | The 2026-10-24 queue wording is plain ("Each item says which pages to look at and what to do"). Pipeline vocabulary remains elsewhere: "Import review" (the ledger tab), "Prepare statements from N files", "Left out by you", "Waiting for a better reader", "Proof standing", "Payment graph" vs "Follow money" vs "Trace funds". |
| 3 | User control and freedom | 3 | Machine reading and correction both kept; autofilled values carry "Undo"; leave-unimported is reversible. No lock on a confirmed period and no explicit unlock (Valid8 has both). Undoing an import is not a single action. |
| 4 | Consistency and standards | 2 | 16 views; "statement", "period", "file", "batch", "import" and "payment" used for overlapping things on one line; individual and batch review paths historically disagreed about readiness (automation plan, 2026-09-28, reproduced). |
| 5 | Error prevention | 4 | Fail-closed saving: 0 wrong admissions on the scored real set in every wave; copies set aside automatically; amounts flagged, never hard-refused. Known live gaps: 2 double-admitted periods, 11 statements saved without their printed page 1. |
| 6 | Recognition rather than recall | 3 | Queue items state what and where. Deep tools hidden under "More financial tools"; an analyst must remember which of five tracing tools answers which question. |
| 7 | Flexibility and efficiency of use | 2 | Grouped confirm for same-answer fields per account (live). No keyboard flow, no "next field needing review", no row proposals, no whole-column repair, no bulk "accept rows on this page". |
| 8 | Aesthetic and minimalist design | 2 | Up to nine panels on the Statements tab; a 5,069-line review panel; seven states in the status line. |
| 9 | Help users recognise, diagnose, recover from errors | 3 | Issue sentences name the page and the missing fact. The issue taxonomy is coarse and sometimes misleading ("balance" for unreadable amounts). Error messages do not point at the first row where the running balance breaks, which Docuritas and Docsumo do. |
| 10 | Help and documentation | 3 | Exhaustive guide with screenshots and troubleshooting. Its size (35,000 words) is the symptom; parts describe flows (e.g. per-file "Ready to review") that the queue-first design has since replaced. |
| | **Average** | **2.7** | |

## 2.4 What the UI does well (keep)

- Boxed source on screen for 99.9% of live transactions.
- Corrected values, never machine values, drive totals, flows and searches; both stay visible.
- Copies set aside and linked rather than deleted or silently ignored.
- The queue shows only what needs a person, each item with page and action (live since 2026-10-24 07:29).
- Exports are byte-reproducible for an unchanged ledger (`export_manifest.py`).
- A combined payments-and-case-events timeline exists in the financial area (`FinancialCaseTimeline`). Links from payments into phone-extraction items were not verified in this audit and are not claimed.

---

# Part 3. Competitive usability benchmark

Sources: two research passes run for this assessment (2026-10-24, web, about 30 minutes each; full notes with every URL in Appendix A), plus the existing dossiers `16-loupe-competitor-dossiers.md` (graph, e-discovery, legal AI), which contain nothing on financial-statement tools. Labels: **(verified: URL)** seen on a vendor help/doc page or third-party page; **(vendor claim)** marketing; **(inferred)** reasoning. Most competitor evidence is vendor documentation; independent reviews barely exist for this category, and **no Reddit or ACFE threads surfaced for any tool**.

## 3.1 The tools that matter, in one line each

| Tool | What it is relative to Loupe | Key evidence |
|---|---|---|
| **Valid8** | Closest established investigator product: statements in, reconciled ledger, transfers, Sankey, indexed PDF report | "Verification" is the balance tie-out (green/yellow), not human checking; PDFs go to an external service, FIFO, "no override available to users or to support" (verified: customersuccess.valid8financial.com/knowledge/account-grid-overview, /-how-long-processing-takes). Pricing not published. |
| **Docuritas** | New (2026) product aimed exactly at "ledger you can defend": running-balance proof, first mismatched row, gaps/overlaps, examiner edits logged by name, bound exhibit with SHA-256 per file and a findings hash per page | All vendor claim (docuritas.com; legaltechnologyhub.com/vendors/docuritas); $999 per matter (verified on page). No reviews. |
| **Altia FIT / Investigator** | UK police standard: OCR re-digitising + analysis toolbar | GBP 4,160-4,690 per licence per year (verified: G-Cloud 14 listing); used by every UK force and by police/prosecutors in Colombia and Panama (reported: thefintechtimes.com). No review process for OCR output described. |
| **i2 Analyst's Notebook** | Link charts from structured data; no statement extraction | Summed links show count and total value per direction (verified: ibm.com/support/pages/node/716175); ~USD 7,160/yr reported (selecthub). |
| **CaseWare IDEA** | Audit analytics; user builds import templates | Learning-curve complaints on G2/TrustRadius; no review queue concept. |
| **DocuClipper** | Low-cost statement converter with reconciliation and flow-of-funds | Opening + deposits - withdrawals = closing per account/period; "edit transactions in place until totals match" (verified: docuclipper.com/features/bank-statement-reconciliation); USD 20.30/60 pages to 279.30/1,800 pages per month (verified: pricing page); "will add support within 48 hours" for unsupported formats (vendor claim); Capterra complaints about small-bank formats and reversed signs. |
| **MoneyThumb** | Statement-tuned OCR where a failed reconciliation triggers a targeted re-read, then highlights the exact values to check | (verified: moneythumb.com/?p=15796; docs.moneythumb.com core concepts) |
| **Ocrolus** | Machine pass plus paid human verifiers; lists Mexico | "US, Canada, Mexico, and the United Kingdom" (verified: docs.ocrolus.com/docs/bank-statements); a 2023 incident left 517 documents overdue because the human verification stage slowed (verified: pingoru.io incident page). |
| **Docsumo** | Exceptions-only review with a typed error taxonomy | Codes for balance discrepancy, date tally, out-of-period rows, likely-cause rows, values taken from the table; errors propagate cell → row → table (verified: support.docsumo.com/docs/bank-statement-review-tips). |
| **Rossum** | Generic document review; best documented keyboard flow | "Automation blockers" panel; Enter jumps to the next field needing review; calibrated per-field confidence (verified: knowledge-base.rossum.ai). |
| **Sensible** | Deterministic per-bank configs plus LLM, sold with a config-writing service | (vendor claim: sensible.so/doc-types/bank-statements). The commercial version of Loupe's per-bank approach. |
| Hummingbird / Unit21 | AML case queues; audit trail references | Hummingbird: audit trail on each case, one-click case export (verified). Unit21: audit trail explicitly omits note and checklist changes (verified: docs.unit21.ai/docs/audit-trails). |
| Palantir, Quantexa, Siren, Nuix, Cellebrite Pathfinder, Penlink | Assume structured data already exists; none turns scanned statements into a ledger | (verified/inferred, research A §6-11) |

## 3.2 Feature and usability matrix (0-5)

Scores for competitors rest mostly on vendor documentation; where no evidence was found the cell says "?" rather than guessing. Loupe scores are for the live product (`68d95b20`), not branches.

| Capability | Loupe | Valid8 | Docuritas | Altia | i2 ANB | IDEA | DocuClipper | MoneyThumb | Ocrolus | Docsumo | Rossum |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (a) Load a folder | 3 | 4 | 4 | 3 | 1 | 1 | 4 | 3 | 4 | 4 | 4 |
| (b) What was read, what wasn't, why | 2 | 4 | 4 | ? | 0 | 1 | 3 | 3 | 3 | 4 | 4 |
| (c) Fix a held statement | 2 | 3 | 3 | ? | 0 | 1 | 3 | 4 | 2 (vendor fixes) | 4 | 5 |
| (d) Duplicates / copies | 4 | 3 | ? | ? | 1 | 2 | ? | 2 | 2 | ? | 3 |
| (e) Account history, gaps | 3 | 5 | 4 | 2 | 1 | 2 | 2 | 2 | 1 | 2 | 0 |
| (f) Follow money | 3 | 4 | 3 | 3 | 5 | 1 | 3 | 1 | 0 | 0 | 0 |
| (g) Search / filter | 4 | 4 | 2 | 3 | 3 | 4 | 2 | 1 | 1 | 1 | 1 |
| (h) Annotate and export exhibit | 3 | 4 | 5 | 3 | 4 | 3 | 2 | 1 | 1 | 1 | 1 |
| (i) Transaction → source page | 5 | 3 | 3 | ? | 0 | 0 | 1 | 1 | 2 | 4 | 4 |
| Coverage, common US formats | 3 | 4 | ? | ? | n/a | 1 | 4 | 4 | 5 | 4 | n/a |
| Coverage, Mexican banks / Spanish | 3 | ? | ? | ? | n/a | 1 | 1 | ? | 2 | 1 | n/a |
| Coverage, new unseen layout | 1 | 4 | ? | ? | n/a | 1 | 3 | 3 | 4 | 3 | 3 |
| Speed to usable ledger | 2 | 3 | 4 | 3 | n/a | 2 | 4 | 4 | 4 | 4 | 4 |
| Trust: wrong values kept out | 5 | 3 | 4 | ? | n/a | 2 | 3 | 3 | 4 | 4 | 3 |
| Trust: audit trail of edits | 4 | 3 | 5 | ? | 3 | 3 | 3 | ? | ? | 4 | 4 |
| Learning curve (5 = easy) | 2 | 3 | 4 | 3 | 2 | 2 | 5 | 4 | 4 | 4 | 4 |

One-line justifications for Loupe and the row leader:

| Row | Loupe | Leader and why |
|---|---|---|
| (a) | Batch reading starts by itself and copies are announced, but production reads take hours and removed files leak into counts | Valid8/DocuClipper/Docsumo: upload and a status per file, nothing else to decide (vendor docs) |
| (b) | Status line mixes 7 states and its "Imported" figure does not match the ledger | Valid8: chevrons All / Unassigned / To Reconcile / Reconciled with counts (verified); Docsumo: only failures, reason attached (verified) |
| (c) | Steps and page per item; fixing means typing rows one at a time, mouse-driven | Rossum: keyboard flow to next field needing review (verified); MoneyThumb: re-reads then points at the exact values (verified) |
| (d) | Automatic linked set-aside of copies, with a "possible copy" comparison | Loupe leads; no competitor documents an equivalent |
| (e) | Per-account history with start/end missing; no case-wide grid | Valid8 Account Grid: bar per statement per account, gaps visible, gaps exported to Excel (verified) |
| (f) | Five overlapping tools | i2: summed links, the court-standard chart (verified); Valid8: transfer matching, "Possible Transfer" for one-sided transfers, Sankey (verified) |
| (g) | Filters, chart-driven filtering, totals only on corrected values | Loupe and Valid8 level; IDEA for raw analytics power |
| (h) | Findings and reports, reproducible exports; long path; no one-click indexed exhibit | Docuritas: bound indexed exhibit, page citation per transaction, SHA-256 per file, findings hash per page (vendor claim) |
| (i) | Boxed value on the source page, 99.9% of live rows | Loupe leads; Docsumo/Rossum show source beside data during review, not for saved rows |
| Coverage US | Navy Federal, M&T, Synchrony, Capital One, Citi etc. via readers | Ocrolus: machine + human verifiers (vendor claim) |
| Coverage MX | BBVA, Santander, Monex, Kapital, Intercam, Scotiabank readers, multi-currency; no competitor names these banks | Loupe leads by default: Ocrolus lists Mexico at country level only; Azure prebuilt is en-US only (verified) |
| New layout | Starts near 0 until a reader exists (M&T 0/41, Synchrony 0/16) | Valid8 "template-free" (vendor claim); Ocrolus via human verifiers; DocuClipper adds formats in 48 hours (vendor claim) |
| Speed | Days to weeks for a production to clear; release-gated | DocuClipper/Docuritas: minutes (vendor claim) |
| Trust: wrong out | 0 wrong admissions on the scored set; fail-closed | Loupe leads; most competitors equate "verified" with "balance ties" |
| Audit trail | Machine and corrected values kept; audit chain module | Docuritas: edits logged by name inside the exhibit (vendor claim) |
| Learning curve | 16 views, 35,000-word guide | DocuClipper: converter, almost nothing to learn |

## 3.3 Where Loupe is genuinely better (live product, evidenced)

1. **Source traceability on every saved transaction.** 99.9% of 29,884 live admitted transactions carry page and rectangle; the detail panel shows the boxed value. No researched competitor documents this for saved rows.
2. **Zero wrong admissions as a hard rule, measured.** 0 wrong on the scored real set in every wave since 2026-10-05, with must-hold statements held (5/5). Competitors' "verified" means the balance ties, which a compensating misread can pass (Valid8's "100% accurate (every statement reconciled to the penny)", vendor claim). Loupe additionally checks identity, page completeness (soon), copies and holder.
3. **Mexican bank coverage that nobody else claims.** Live BNB2: BBVA 496 periods, Intercam 134, Monex 120, Santander 112, Kapital 53, Scotiabank 5, in up to 4 currencies per bank. No researched vendor names any of these banks.
4. **Copies handled as evidence, not deleted.** 265 copies set aside and linked across the two big cases. Ocrolus, by contrast, deduplicates same date + description + amount within a book automatically (verified), which would delete genuine repeated payments in forensic work.
5. **Correction model.** Machine reading and correction both kept and visible; only corrected values in totals, flows and searches. Docuritas claims edit logging; nobody else documents the dual-value rule.
6. **Reproducible exports** (identical ledger, identical bytes). Docuritas is the only competitor with a comparable claim (findings hash).

What is **not** a demonstrated advantage today, despite being planned or claimed internally: one model joining phone, financial and documents (a payments-and-case-events timeline exists; cross-links to phone extractions were not verified); speed; coverage of unseen layouts.

## 3.4 Where others are better (blunt)

1. **They tell the analyst where the ledger has holes, on one screen.** Valid8's Account Grid (one bar per statement per account over time, yellow when it does not tie, gaps as empty space, export of all gaps) answers "what do we have and what is missing" in one look and produces a records-request list. Loupe answers this one account at a time.
2. **They make a failed statement quick to fix.** Docsumo shows only failures, names the rule that failed, marks the likely-cause rows, and re-runs the check after each edit; MoneyThumb re-reads and points at the exact values; Rossum moves from field to field on the keyboard; DocuClipper lets you edit in place until totals match. Loupe's held statement is a long form, mouse-driven, and a missed page means typing every row.
3. **They point at the first broken row.** Docuritas reports "the first mismatched row and the amount"; Docsumo flags per-row running-balance failures. Loupe's issue sentence says "balances" without locating the break.
4. **New formats do not wait for a release.** DocuClipper promises 48 hours; Valid8 claims template-free reading; Ocrolus puts humans behind the machine. In Loupe a new layout waits for a reader to be written, benched for hours, reviewed and deployed, and deploys defer while reading runs.
5. **Their exhibit is one button.** Docuritas and Valid8 produce an indexed PDF where every transaction cites file and page; Docuritas adds hashes. Loupe has the underlying data (better source boxes than either) but no single exhibit output.
6. **Their status is honest at a glance.** Valid8's chevrons (All / Unassigned / To Reconcile / Reconciled) are four mutually exclusive counts that add up. Loupe's status line has seven partly overlapping counts and an "Imported" figure that does not add up to the ledger.
7. **Lock on confirm.** Valid8 locks a reconciled statement and requires "Unreconcile" to edit; Unit21 freezes a case "in review". Loupe has no equivalent.

## 3.5 The coverage question

**How the leaders get high coverage.** Not from better extraction alone. They (1) put humans behind the machine and sell the combined output (Ocrolus); (2) still write or train per-format, but faster and as a service (Sensible configs, DocuClipper's 48 hours, Klippa per-bank training); (3) accept lower precision and use the balance check plus a fast review screen to catch the rest (DocuClipper, Docsumo, MoneyThumb); (4) use the failed balance as a trigger to re-read (MoneyThumb; Reducto's "iterate until it balances", which is dangerous for evidence because it pushes the model to produce numbers that balance). Self-reported unattended rates: Heron about 90% (2022, vendor claim, source now 404), Docsumo and Sensible "95%+" (vendor claims), all on US lending documents, mostly digital PDFs. **Nobody credible claims 100% unattended, and nobody documents Mexican bank coverage.**

**What that implies for Loupe.** Loupe's safety model is better than the market's; its coverage model is worse. The two can be separated. The arithmetic gate (opening + rows = closing, identity, page completeness, copies) is reader-agnostic: it does not care who produced the rows. So the reader per layout is not what makes Loupe safe; the gate is. That means the expensive part of the current programme (writing and benching readers quirk by quirk) can be replaced for the long tail without weakening safety.

**Recommendation.**
1. **Make a vision/LLM reader the default first pass for any statement no proven reader saves**, not the last item in the queue. Order: proven reader → if held, vision reader → same gate → if still held, Alex, with the vision reading pre-filled as row proposals she confirms per page.
2. **Keep per-bank readers only for the high-volume layouts they already serve** (BBVA, Santander, Monex, Navy Federal, M&T, Capital One...). Stop writing new ones by default; write one only when a layout is high-volume and the vision path measurably fails on it.
3. **Guards on the vision path** (from research B and the existing approval): rows tagged "read from page image" with page; the model is never given the target balance; per-row running-balance check wherever the statement prints one (this catches compensating errors that a period total misses); opening must equal the previous statement's closing; pinned model version, stored raw response and hash, no silent re-runs; never overrides a proven rule reading; 0 wrong / 0 lost on the truth set before going live.
4. **Measure it on the real residue**: the 133 + 137 waiting statements and the 18 OCR-damaged BBVA scans, reporting proven / held / cost per page.

**Risks, stated plainly.**
- On OCR-damaged pages the text layer is the thing that is wrong, so "the value must match the text at that spot" cannot be used as a check there; arithmetic is the only verifier, and two compensating errors (a dropped row and an invented row of the same amount; a swap between two equal amounts) pass a period total. The per-row running-balance check is the mitigation and only exists where the bank prints running balances.
- Determinism: a re-run can give different rows. Store and pin.
- Privacy: case page images go to OpenAI. Neil approved this on 2026-10-24 and Loupe already sends case data through the same path; zero-data-retention terms should be confirmed for production material under protective order.
- Cost: published per-page prices for comparable services run about USD 0.01-0.34 (research B); at the ~300 held statements in question this is small next to analyst time (inferred).

---

# Part 4. Prioritised improvement list

## Fix in the next two weeks

| # | Problem | Evidence | Best competitor practice | Proposed change | Effort | Expected impact on Alex |
|---|---|---|---|---|---|---|
| 1 | Two BNB2 periods counted twice in the live ledger | real/STATE.md open decision 3; fix on unmerged `fin/r15-hold-gaps` | Valid8 flags overlapping statements (verified) | Repair the live pair; merge the cross-account copy rule | S | Totals and flows on BNB2 become correct |
| 2 | Built work not landing; parallel rebuilds | 22 unmerged `fin/*` branches; wave 15 left on `fin/release-1`; missing-pages gate built twice | n/a | One release branch; land or delete every open branch this week; one coordinator | S | Fixes reach her instead of sitting in branches |
| 3 | Live statements read by old readers never get the new readers | 99 of 155 waiting were in truth, bench saved 50; autofill made 0 of 27 ready on stale keys | n/a | Ship `rd-release1` (automatic re-preparation of held items), then re-read every live held statement | S-M | Simulated −18 on BNB2 now; more as readers improve |
| 4 | Her own touched statements are frozen | 83 originals / 93 items protected | Docsumo/DocuClipper: re-run checks after edit | Finish and ship carry-edits (her values win, conflicts shown) | M | The largest single lever on the BNB2 residue (up to ~90 items) |
| 5 | Queue headline does not match the ledger | "Imported 2,157" vs 1,187 periods | Valid8 chevrons with counts that add up | Count statement periods, not batch entries; show 4 mutually exclusive numbers: In the ledger / Needs you / Loupe is working on it / Copies | S | She can say what is done and what is left |
| 6 | "Waiting for a reader fix" and "rechecking" give no horizon | 14 in Erica Hopper | Ocrolus: escalate one document to the stronger tier from the queue | Replace with either an action for her or "Loupe will try again on <date>"; never an open-ended wait | S | No dead ends in her list |
| 7 | Rows typed one at a time | 58% of residual actions; `r15-batch-work` built, default off | MoneyThumb points at exact values; Docsumo whole-table repair | Turn on page row proposals (prefilled, confirmed per page only when they chain from opening to closing) | S-M | Cuts the largest class of manual work |
| 8 | Issue labels misdescribe the problem | 43 of 80 "balance" holds were unreadable amounts | Docsumo typed error codes; Docuritas first mismatched row | Split "balance" into "amounts unreadable on page N" vs "opening/closing missing"; name the first row where the running balance breaks | S | She goes straight to the right place on the page |
| 9 | Erica Hopper has had no queue attention | 137 waiting + 14 reader fix + 15 unreadable; 30% automatic | n/a | Run the same reader-gap and re-read treatment on it | M | The second live case moves |

## Structural

| # | Problem | Evidence | Best competitor practice | Proposed change | Effort | Expected impact on Alex |
|---|---|---|---|---|---|---|
| 10 | Coverage built layout by layout; unseen layouts start near 0 | M&T 0/41, Synchrony 0/16 before readers; generic engine alone 72% | Valid8 template-free (vendor claim); Ocrolus machine + humans; DocuClipper 48-hour formats | Vision reader as the default first pass for anything a proven reader does not save, behind the existing gate (3.5) | L | The only credible path to a residue small enough to clear in a sitting |
| 11 | No case-wide view of what is covered and what is missing | Coverage is per account | Valid8 Account Grid with gap export (verified) | Account × month grid for the whole case: green proven, amber needs her, grey missing; export the missing periods as a list | M | Shows holes in the evidence at a glance and gives her a list of what is missing |
| 12 | Fixing a held statement is slow and mouse-driven | One key handler in a 5,069-line panel | Rossum keyboard flow; Docsumo exceptions-only with live re-check | Rebuild the held-statement screen around the page: source left with boxes, rows right, the failing rows highlighted, Enter = next problem, totals re-checked on every edit | L | Minutes per statement instead of a long form |
| 13 | No one-button exhibit | Report path is 10 steps | Docuritas bound exhibit with page cites and hashes; Valid8 indexed PDF | "Exhibit for this account/period/finding": indexed PDF, page citation and boxed thumbnail per transaction, file hashes, list of hand corrections | M | Court-ready output from what Loupe already knows better than competitors |
| 14 | Metric and release process built around the bench | 95.6% bench vs 62%/30% live automatic; 9-hour benches; deploy needed 16 attempts | n/a | Headline = live "needs Alex" per case and 0 wrong; bench as a regression gate only; a smaller fast truth subset for every change, the whole set nightly; deploy without waiting on reading jobs (drain or queue) | M | Releases reach her in hours, and progress is measured in her terms |
| 15 | Sixteen views, five tracing tools, a 35,000-word guide | Part 2 | Valid8 docs organised as Load → Confirm → Match → Analyse | Re-cut navigation around the four jobs: Get the statements in → Make the ledger right → Follow the money → Report; fold the five tracing tools into one with modes | M-L | Less to learn; the screen tells her the next step |

---

# Appendix

## A. Sources

Internal (read for this assessment):
- `/mnt/owl-data/fin-wt/headless/STATUS-FOR-NEIL.md` (2026-10-24 ~20:00)
- `/mnt/owl-data/fin-wt/headless/real/ALEX-QUEUE-WORK.md`, `real/STATE.md`
- `/mnt/owl-data/fin-wt/headless/rd-finish.md`, `rd-takeover.log`
- `docs/financial-workflows/`: automation-delivery-plan-2026-09-28.md, baseline-2026-10-02.md, baseline-v4-2026-10-02.md, error-register-2026-09-27.md, automation-workfile.md (dates)
- `/mnt/owl-data/fin-wt/notes/`: r5-alex-feedback.md, r7-alex-queue-explainer.md, alex-1013.md
- Memory: project_loupe_financial_automation.md, feedback_no_regression_merges.md, feedback_rebuild_not_push_features_first.md
- Git: `git log --since=2026-08-01` (financial paths), `git branch` (fin/*), `git log HEAD..<branch>`
- Frontend: `frontend_v2/src/features/financial/` (FinancialNavigation.tsx, FinancialPage.tsx, ReviewQueuePanel.tsx, StatementImportPanel.tsx, SourceHighlight.tsx, TransactionSourceHighlight.tsx, AccountHistory.tsx, StatementCoveragePanel.tsx, FinancialCaseTimeline.tsx); `public/docs/financial-guide/financial-user-guide.md`; `public/docs/financial-testing/financial-team-checklist.md`
- Backend: `services/financial/review_queue.py`, `export_manifest.py`

External: full notes with every URL and label in
- `/mnt/owl-data/fin-wt/headless/fin-assess-research-A.md` (forensic and investigator tools: Valid8, IDEA, Arbutus, ActiveData, i2, Nuix, Pathfinder, Penlink, Siren, Quantexa, Palantir, Chainalysis Reactor, Hummingbird, Unit21, CLEAR, Docuritas, Altia, Prism339, Cuadra, Hong Kong Police systems)
- `/mnt/owl-data/fin-wt/headless/fin-assess-research-B.md` (extraction: Ocrolus, Inscribe, DocuClipper, MoneyThumb, Heron, Veryfi, Rossum, Docsumo, Nanonets, Klippa, Reducto, Sensible, Mindee, ABBYY Vantage, Azure, Google Document AI, AWS Textract)

Key URLs cited in the body: customersuccess.valid8financial.com/knowledge/account-grid-overview; customersuccess.valid8financial.com/knowledge/-how-long-processing-takes; customersuccess.valid8financial.com/knowledge/bank-statement-troubleshooting; docuritas.com; legaltechnologyhub.com/vendors/docuritas; applytosupply.digitalmarketplace.service.gov.uk/g-cloud/services/148862043335266; ibm.com/support/pages/node/716175; docuclipper.com/features/bank-statement-reconciliation; docuclipper.com/pricing; moneythumb.com/?p=15796; docs.ocrolus.com/docs/bank-statements; pingoru.io/providers/ocrolus/incidents/2245729; support.docsumo.com/docs/bank-statement-review-tips; knowledge-base.rossum.ai/docs/document-validation-screen-in-rossum; sensible.so/doc-types/bank-statements; learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/bank-statement; docs.unit21.ai/docs/audit-trails; help.hummingbird.co (audit features page).

## B. Queries run (all inside `SET TRANSACTION READ ONLY`, asserted `transaction_read_only = on`, rolled back)

1. Per-case transactions, batches, batch-item statuses, statement periods and reconciliation status.
2. `services.financial.review_queue.case_review_queue(case_id, use_cache=False, limit=0)` for all six cases (the same function the queue screen uses), for counts, issue counts and status line.
3. Current ledger periods (source document not superseded, status admitted) joined to `financial_ingestion_runs.started_by_email` to split automatic (`auto-save@system.local`) from Alex's imports; by bank via `financial_accounts.institution_name`; by week.
4. Distinct imported statement keys and files per case (to test the "Imported" headline).
5. `financial_import_operations` by actor and day (Alex's activity).
6. `financial_transactions.provenance->'locator'` keys over admitted rows (source-box coverage).
Scripts: `/tmp/fa-<user>/q.py`, `/tmp/fa-<user>/rq.py` (scratch, not committed).

## C. Screenshots

None taken. No test login exists in the repository or docs, and forging a session token for the live system was ruled out. The in-app guide's 47 synthetic screenshots are in `frontend_v2/public/docs/financial-guide/images/`.

## D. Method notes and limits

- "Saved by Alex" counts imports she started, with or without edits; the database does not distinguish a one-click import from an edited one for the older imports.
- Live periods use current, admitted source documents only; superseded readings are excluded (they are excluded from the ledger too: `ledger_status`).
- Bench and census figures are quoted from the workfiles, not re-run (no benches on this host by instruction).
- Competitor scores are judgements from vendor documentation, not hands-on trials; "?" means no evidence found.
- Click counts are from code and the guide, not from a live session.
