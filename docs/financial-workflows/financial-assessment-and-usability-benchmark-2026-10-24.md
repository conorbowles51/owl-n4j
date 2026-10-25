# Loupe financial: state assessment and usability benchmark (live application)

Date: 2026-10-25. Scope: **BNB2 only** (Neil, 2026-10-25 00:37 UTC: BNB2 first, every other case deferred until BNB2 works for Alex).
Live code during the walkthrough: `682ce6bb` then `f81d5aff` (deployed 2026-10-25 02:21 UTC); the live app was redeployed six times between 00:50 and 02:50 while this was being measured (Appendix D).
Every statement about Loupe below comes from one of three sources, named where it is used: **(seen)** a logged-in session on the live app, **(measured)** a read-only query against the live database or the live queue function, **(log)** the run logs of the people building it. Nothing is taken from reading source code alone.
Method: a view-only login on the live app, driven by a headless browser that blocks every write request (Appendix B); live database queries inside `SET TRANSACTION READ ONLY`; the live ledger audit of 2026-10-25 01:20 UTC.

## Bottom line

BNB2 is safe and mostly built, but the live app is not yet something Alex can work in comfortably. **Measured at 02:45 UTC: 1,208 statement periods are in the ledger, 65% saved with no human action, 26% saved by Alex, and 121 statements (9%) are still outstanding, of which 107 wait for her.** The ledger is trustworthy where it has been checked: the latest live audit agrees with the answer key on 650 BNB2 periods and disagrees on 1, no statement is counted twice, and 99.0% of the 24,159 saved payments open on their source page with the printed line boxed in red (seen). The page-image reader is live for BNB2 and has saved 6 held statements (220 payments) with 0 wrong out of 65 it tried. What does not work is the experience around that ledger. In the walkthrough the main screens took **30 seconds to 4 minutes** to load; the review queue failed outright three times with "signal is aborted without reason"; two status panels failed on every visit; one screen shows raw database error text; counts disagree between tabs (66 accounts and 12 banks on one, 260 accounts and 14 banks on the next); and a queue item that says "rows could not be read on page 12" opens a statement whose every arithmetic check passes. Competitors with weaker safety are ahead on exactly these things: fast, honest status, one case-wide coverage view, exceptions-only review that points at the broken row, and a one-button exhibit. **Recommendation: for the next week, stop adding reading capability and make the live app fast, stable and consistent for the 107 statements in front of Alex** (one deploy window a day, queue and status panels that load in seconds, one set of counts, queue headlines that match the statement), resume the paused re-reading so the carry-edits work already live can act, and route held statements through the page-image reader by default. Expected effect: the waiting count is set mainly by the re-read and page-image steps, and the session quality by the stability work; neither has a measured forecast yet.

## Contents

- Part 1. Where the financial work actually is (BNB2)
  - 1.1 What is live, built, paused
  - 1.2 Coverage measured on the live system
  - 1.3 Live versus bench
  - 1.4 Trend
  - 1.5 Why the same issues keep coming back (root causes, ranked)
  - 1.6 Decisions with recommendations
  - 1.7 Realistic outlook
- Part 2. Usability audit of the live financial UI (logged-in walkthrough)
- Part 3. Competitive usability benchmark
- Part 4. Prioritised improvement list
- Appendix A. Sources. B. Method and safety. C. Screenshots. D. Timings and restarts. E. Limits.

---

# Part 1. Where the financial work actually is (BNB2)

## 1.1 What is live, built, paused

| State | What | Evidence |
|---|---|---|
| **Live** (`f81d5aff`, 2026-10-25 02:21 UTC) | Reader fixes, missing-pages hold, automatic fill of known answers, BBVA credit-line rows, copies across accounts set aside, page row proposals (all from `081bdcf0`); race fixes (`606fe0d9`); page-image reader for held statements, BNB2 only, by approved-case list (`f203ac72`, `dbf9e14e`, `f81d5aff`); carry-edits, first version and the settle-with-saved-statement fix (`f203ac72`, `682ce6bb`); replacement of a wrong saved statement by a proved fresh reading (`f257abb9`); credit-line application date (`1f762cc7`); the case's usual currency accepted when no currency is printed (`682ce6bb`). | `deploy/logs/.last-good-commit`; real/ALEX-QUEUE-WORK.md lines 2026-10-25 01:04 to 02:42 (log) |
| **Live but switched off** | Automatic re-preparation of held statements after a reader change (paused by Neil 2026-10-25 01:30-01:35 until the four fix jobs deployed). Carry-edits acts only through that re-preparation, so its live effect is **0** until it is resumed. | ALEX-QUEUE-WORK.md 01:30 and 02:42 CARRY lines (log); queue shows "Being rechecked 0" at 02:45 (measured) |
| **Measured but not yet acting** | Carry-edits read-only simulation on BNB2: statements refused because of Alex's own work 71 → 35; 30 originals carried (20 settle as already saved, 10 need her check); saved data changed 0. | ALEX-QUEUE-WORK.md 02:42 (log) |
| **Not built, proposed by the build runs** | Page-image readings offered to Alex as one-click answers on the 16 statements where she has saved work; accepting a first statement's header when page-image and text readings agree (9 in BNB2). | STATUS-FOR-NEIL.md, Vision reader section (log) |
| **Branches** | 131 `fin/*` branches; 12 carry commits that are not in live (newest `fin/rd-carryedits` and `fin/aq-b-santander`, 2026-10-24; wave-15 branches 2026-10-23). This assessment did not check which of the 12 are superseded. | `git rev-list f81d5aff..<branch>` |

## 1.2 Coverage measured on the live system (BNB2)

Definitions: "Saved automatically" = the ledger period was written by auto-save with no click. "Saved by Alex" = written by an import she started (this includes one-click imports of statements that needed no edit). "Outstanding" = waiting for Alex + ready but not saved + could not be read + being rechecked. Copies and "not a payment statement" are excluded.

| Measure (2026-10-25 02:45 UTC, live `f81d5aff`) | Count | Share of 1,329 |
|---|---|---|
| Current ledger periods | 1,208 | |
| Saved automatically | 859 | **65%** |
| Saved by Alex | 348 | 26% |
| Replaced by a proved fresh reading (System) | 1 | 0.1% |
| Waiting for Alex | 107 | 8% |
| Ready, not yet saved | 10 | 1% |
| Could not be read | 4 statements (+1 file) | 0.3% |
| Being rechecked | 0 (re-reading paused) | |
| **Needed or still needs Alex** | **469** | **35%** |
| Copies set aside (not counted) | 82 | |
| Not a payment statement (not counted) | 13 | |
| Saved payments | 24,159 | |

Why statements wait (queue issue counts, measured 02:45; one statement can carry more than one): reading (rows or pages unreadable) 28, currency to confirm 25, balances 24, earlier saved review work 6, holder 6, no activity 6, bank name 5, account number 5, pages missing 2. The build run's own breakdown by main reason at 02:23: the reading needs checking 61, currency not printed 25 (10 clear when re-reading resumes), her saved work 6, no-activity confirmation 6, balances disagree 4, holder 2, pages missing 2, account number 1 (STATUS-FOR-NEIL.md, log).

What the queue asks her to type (seen, first page of the queue, 47 items at 00:50): the item texts name **94 unreadable rows** (each a date, an amount and a direction) and **11 single fields** (bank, holder, account number, a balance) to enter, plus currency confirmations that can be answered once for several statements ("One answer for 2 statements"). The largest groups of headlines: "The balances do not add up" 10, "Enter at least one printed opening or closing balance to save a statement without transactions" 7, "Confirm the currency" 5, "Your saved corrections were made before Loupe read the PDF again" 4, "A row added by hand needs its page" 4.

Ledger quality (measured):
- Live audit against the answer key, 2026-10-25 01:20 UTC, BNB2 families: **650 periods agree, 1 disagrees** (a BBVA statement whose balances differ from the answer key; the current reader reads it the same way, so automatic replacement does not apply), 65 saved periods have no period dates and cannot be compared, 2 are overlap trims of online movement queries, 3 have no answer-key period. 0 printed periods saved twice; 0 saved into two ledger accounts. One wrong Monex save (0 payments) was replaced by the proved fresh reading (7 payments) at 01:25.
- 65 current saved periods have no period start date and 65 have reconciliation "unavailable"; 0 are unbalanced.
- 23,928 of 24,159 saved payments (99.0%) carry a page and a rectangle; 231 carry the page only, of which 220 are the page-image reader's rows.
- Known saved defects not yet acted on: 11 saved BBVA statements missing their printed page 1; one saved statement that may carry the wrong currency (STATUS-FOR-NEIL.md, log).

Page-image reader, live (measured 02:53 and log 02:42): 65 BNB2 statements read from their page images; **6 proved and saved (220 payments), 0 wrong**; 56 not proved, 3 failed. Of 52 reading or balance holds diagnosed: 14 pages missing, 16 Alex's saved work (deliberately not read), 4 no earlier saved statement to confirm against, 3 unbalanced, 3 no payment section, 5 file preparation errors, 7 other. Cost USD 0.020 a page, about USD 0.11 a statement, USD 7.09 for 347 pages.

The other five cases, including the second large case, are deferred until BNB2 works (Neil, 2026-10-25 00:37).

## 1.3 Live versus bench

The bench of record (wave 14) says 95.6% of verified real periods are ready with no edit and 0 wrong. That figure is a fresh read of documents with an answer key. It does not describe BNB2's queue, for reasons that are visible live:
- **Re-reading is paused.** Statements prepared by older readers are not re-prepared until it resumes; "Being rechecked" is 0 (measured).
- **Alex's own earlier work holds statements back.** 6 statements wait on "saved corrections made before Loupe read the PDF again" (measured); the carry-edits simulation moves 36 statements off this hold once re-reading resumes (log).
- **The bench excludes the hardest documents** (unverified, unscored and incomplete ones), and the live queue is mostly those: OCR-damaged scans, missing pages, first statements of an account.
- **The bench has no copies, saved-review conflicts, deploys or host load.** The live app has all four, and Part 2 shows they decide what Alex experiences.

The measure Neil set ("BNB2's live waiting count falls, 0 wrong") is the right headline. The bench is a regression gate.

## 1.4 Trend (BNB2, live queue as Alex sees it)

| Time (UTC) | Waiting for Alex | Being rechecked | Ready | Copies | Saved ("Imported") | Source |
|---|---|---|---|---|---|---|
| 2026-10-15 17:40 | 346 | | | 159 | 1,532 | r7-alex-queue explainer |
| 2026-10-23 23:05 | 155 | | | 105 | 2,014 | ALEX-QUEUE-WORK |
| 2026-10-24 20:35 | 133 | 0 | 8 | 93 | 2,157 | measured |
| 2026-10-24 22:52 | 97 | 27 | 10 | 89 | 2,167 | log |
| 2026-10-25 00:39 | 96 | 20 | 10 | 89 | 2,181 | measured |
| 2026-10-25 01:43 | 110 | | | | | log |
| 2026-10-25 02:45 | 107 | 0 | 10 | 82 | 2,197 | measured |

Reading it plainly: the big fall (346 → about 100) came from bulk re-reading and auto-save. Since the 22:07 release the count has moved between 96 and 110; the rise after 00:39 is the 20 statements that were being rechecked landing back in "waiting" once re-reading was paused. The next fall depends on resuming re-reading (carry-edits, 10 currency statements that clear on re-read) and on the page-image reader reaching the 62 statements it had not yet been offered at 01:15 (log).

## 1.5 Why the same issues keep coming back (root causes, ranked by impact on Alex today)

**1. The live app is slow and unstable under the current host load and deploy cadence.** (Highest impact on her experience.) In the walkthrough (seen, Appendix D): Statements & accounts took 91 to 242 seconds to settle on a cold load; the Overview 35 to 104 seconds; People & businesses 137 seconds once. The queue request is abandoned by the browser after 60 seconds and the screen then shows "signal is aborted without reason" and a Try again button; this happened on three separate loads. The app was redeployed six times in two hours; each deploy stops the frontend and backend, and an open screen then shows "Failed to fetch" or "Transactions could not be loaded. Refresh this page to try again." Each build run deploys its own unit as soon as it passes review.

**2. Coverage is still built per layout, and the general route for what readers hold has only just started.** The page-image reader is live but proves 6 of 65 statements so far; most of its holds are by design (pages missing, Alex's saved work, no earlier statement to confirm against) and two of those are rules waiting on a decision (1.6).

**3. The screens show the pipeline's numbers, not one consistent picture of the case.** Seen on the same session: Overview "66 accounts · 12 banks"; Transactions "260 accounts · 14 banks", "166 accounts need identifying", "154 accounts with bank not identified"; the queue heading "Needs (93)" over a status line saying "Waiting for you 89"; "Imported 2,197 statements" against 1,208 statement periods in the ledger; the latest batch "1,466 saved to Financial · 219 files need recovery". The same bank appears under several spellings and counts as several banks; some accounts are named after the PDF they came from with "Bank not recorded".

**4. The queue's instructions and the statement screen can disagree.** Seen: a queue item headed "Some rows could not be read on page 12 … Read each highlighted row" opens a statement whose opening, closing, running balances (21 intervals, 0 differences) and printed credit and debit totals all match; the only thing actually blocking it is a checkbox to confirm she compared an older saved review. The statement opens on page 1, not page 12 (reproduced at 02:53 on `f81d5aff`).

**5. Fail-closed is right and is kept; the residue path for her is still slow.** Fixing a held statement is still field by field and mouse-driven; no keyboard flow was found; rows are typed one at a time.

**6. Work forks and lands faster than it can be absorbed.** Six deploys in two hours on 2026-10-25 from four parallel build runs; re-reading paused to let them land; 12 older branches still carry unlanded commits.

**7. Decisions queue on one person.** Six open items in STATUS-FOR-NEIL.md, including two that change acceptance rules (1.6).

## 1.6 Decisions with recommendations

| # | Decision | Recommendation | What would reverse it |
|---|---|---|---|
| 1 | Resume automatic re-preparation of held statements | Resume now that the four fix jobs are live; carry-edits and 10 currency statements act only through it | A traceback or a wrong save in the first sweep |
| 2 | Deploy cadence | One deploy window a day, outside Alex's working hours, batching every unit that passed review | Neil needs a specific fix live sooner for a live wrong save |
| 3 | Page-image reading on statements she has worked on (16) | Read them; offer each proved reading as a one-click answer beside her version; never save over her work | A proved reading that disagrees with her saved values on the answer key |
| 4 | First statement of an account (9 in BNB2) | Accept the header when page-image and text readings of the same file agree on full account number, holder and bank | Any case on the answer key where both readings agree and are wrong |
| 5 | 1 saved BBVA period that disagrees with the answer key; 11 saved BBVA statements missing printed page 1; 1 possible wrong currency | Put each in her queue as a single check showing both readings; do not un-save | None needed: it costs her minutes and closes known gaps |
| 6 | Kapital statements naming UDIS funds (6) | Leave with Alex; the currency is a judgement | A rule from Neil on UDIS |
| 7 | Headline metric | Report only BNB2 "waiting for Alex", "wrong saves" and screen load time | None |

## 1.7 Realistic outlook

"Alex unblocked" on BNB2, measurable: the waiting count is small enough to clear in one sitting (under about 30), every item opens on the right page with an instruction that matches the statement, every screen she needs loads in under about 10 seconds, and nothing saved is wrong.

| Path | What it takes | Range (estimate, not a measurement) |
|---|---|---|
| Resume re-reading, keep current readers | Decision 1 | Waiting falls by the carry-edits and currency effects (tens, per the simulations); the rest stays |
| Plus page-image reader on every held statement, decisions 3 and 4 | Already built for most of it | The only path with a credible chance of getting under about 30; its live hit rate so far is 6 of 65, held mostly by rules rather than by reading failures |
| Plus stability and consistency work (Part 4 items 1-5) | Days, not weeks | Does not change the count; decides whether she can work through it |

---

# Part 2. Usability audit of the live financial UI

Method: a view-only user logged in to the live app (`http://10.142.0.5:5174`) and walked BNB2 in a headless browser at 1600×1000, between 00:40 and 02:55 UTC on 2026-10-25, with every write request blocked (Appendix B). The user sees a read-only banner ("This case is read-only…") and cannot save, so editing steps were walked up to the save button and stopped. Times are wall-clock from navigation until the screen stopped loading. The host load average was 5 to 9 during the walk. Screenshots are kept outside git (Appendix C); screens are described in words here.

## 2.1 Size and shape of the surface (seen)

| Fact | Value |
|---|---|
| Top-level financial tabs | 7 (Overview, Statements & accounts, Transactions, People & businesses, Follow money, Trends, Findings & Observations) plus "More financial tools" |
| Sub-tabs on Statements & accounts | Review queue, Statement files, Review accounts, Processing batches |
| Additional views reached through the menu | Follow-money modes (FIFO, LIFO, one receipt to several payments, across currencies), Trace one account / between accounts, Transfers between accounts, Payment connections graph, Patterns, Payments in case context, excluded transactions, decisions, ledger runs |
| Status line on the queue | "Total 2416: Imported 2181 · Waiting for you 89 · Ready to import 10 · Copies set aside 90 · Couldn't read 4 · Being rechecked 28 · Left out by you 1 · Not payment statements 13 · Files removed from Financial 211" (00:50). The first eight now add up to the total. |
| Keyboard | No keyboard shortcuts for review were found; "Previous / Next statement with issues" buttons move between held statements |

## 2.2 The analyst's core jobs, walked

| Job | What happened (seen) | Clicks / wait | Friction |
|---|---|---|---|
| **(a) What's in the case, what got read and what didn't, and why** | Overview: money in and out per currency, a flow summary, "Which months do we have?" listing accounts with each month marked Covered or Missing (e.g. "15 of 20 months missing" with the list of missing months). Statements & accounts: the status line above, "Reading 1449 of 1452 files…", the queue split "Needs <name> (93)" and "Loupe is handling (141)", filter chips by reason. | 1 click; Overview 35-104 s, Statements 91-242 s (cold) | "Your statements: Statement status could not be loaded" on every Overview visit; Statement files: "Statement import status could not be loaded" and "1651 files in Financial · … files have saved statements" with the number missing. "Needs (93)" vs "Waiting for you 89". "Imported 2,197 statements" vs 1,208 periods. Processing batches: "1233 of 1452 files checked · 219 files need reading or preparation recovery · 1466 saved to Financial · 125 prepared reviews unfinished". "Checking older uploads for missed payments: Paused · 85 of 91 files checked". The ledger runs view lists "205 attempts to load evidence into this ledger have not finished", each marked "Broke" with raw database text ("OperationalError: (psycopg.errors.DeadlockDetected) deadlock detected DETAIL: Process … waits for ShareLock…"). |
| **(b) Open a held statement and see what to do** | Queue item: a plain headline, three numbered steps naming the page, "Loupe checks it again and imports it by itself once everything adds up", then "After that, also: …" listing further problems, and one action button ("Open page 12", "Enter the bank name", "Compare corrections", "Choose the page"). Clicking it opens the statement inside the tab: a sticky "To fix" box, "Statement 8 of 50 waiting for you", Previous/Next statement with issues, the reconciliation block (printed opening, money in, money out, calculated and printed closing, running-balance intervals, printed credit and debit totals, each "matches" or not), the PDF page beside the extracted rows, header fields (holder, account number, currency, bank, period), "Add a missed transaction", and Import / Save for bulk import (disabled for this user: "You need editing access to this case to confirm an import"). | 1 click from the queue; 19-128 s to open | The example in 1.5 item 4: headline says unreadable rows on page 12, every check on the screen matches, the real blocker is "I have compared the previous saved review"; the PDF opens on page 1. The sticky "To fix" box covers the top of the PDF page while scrolling. Amounts in the reconciliation block are printed without thousands separators (a ten-digit figure reads as one unbroken string of digits). Across the first 47 items: 94 rows and 11 single fields named to type. |
| **(c) Duplicates and copies** | "Copies set aside 82" in the status line; the decisions view lists "Hidden as a duplicate … The same printed statement was saved twice with equal payments and printed balances. This copy is set aside as a linked duplicate; the retained copy counts once", and the reader-replacement decision, each with who and when. | 1-2 clicks | The decision rows identify the statement by an internal document ID, not by account, period or file. |
| **(d) An account's full history and balances** | Review accounts: "Do you have all the statements?" with "3 Accounts with gaps · 0 overlapping · 18 with dates still to check" ("Counts cover the accounts on this page"), then per account the missing date ranges ("2025-05-01 to 2026-04-30 · 365 days"). Overview "Which months do we have?" gives the same per account by month. | 2 clicks; Review accounts 84 s | Several accounts are titled with a PDF file name and "Bank not recorded … No usable imported statement dates. This account's coverage is unknown." No case-wide account-by-month grid; the gap counts cover one page of accounts. |
| **(e) Follow money** | Follow money: "What do you want to follow?" (who paid in and out, FIFO, LIFO, one receipt followed by several smaller payments, across currencies); a paid-in-by / accounts / paid-out-to summary per currency with careful wording ("They do not connect a particular receipt to a withdrawal"); "2989 times money arrived and the next payment left within a week". People & businesses: 742 names and accounts. | 1 click; 21-38 s; People & businesses 18-137 s | **20,802 of 24,159 saved payments (86%) have "Counterparty not identified"**, including transfers whose descriptions print the sender's name and account ("Nombre del Ordenante: …"); these show "From Not identified". The graph, tracing and patterns tools each start from an empty account-and-date form. |
| **(f) Search and filter transactions** | Typing a description into "Search payments" returned 82 matching payments in 3.5 s, with totals per currency for exactly those rows, "Download CSV (82)", filters by person, bank, account, category, amount, date. | Tab 29-89 s, then 1 typing step | The filtered summary still says "260 accounts · 14 banks" and shows empty totals blocks for 146 accounts with no matching payments. "Category list unavailable" appeared once. |
| **(g) Trace a transaction to its source page** | "Details" on a row, then "Open original statement" opens a side panel: date, amount, counterparty, category with its source ("Suggested from the transfer wording"), printed balance, file reference, and the PDF page with the printed line boxed in red ("Show highlighted value"). | 2 clicks; 3.4 s | Works. For rows read from page images: "Read from page 1. The position on the page was not captured for this row. The page is shown without a highlight." |
| **(h) Export, report, exhibit** | "Download CSV (n)" on Transactions; Findings & Observations lists saved observations with supporting payments; Reports: "Create a report from financial findings", no saved financial reports. | Not exercised end to end (creating a report is a write) | No single exhibit output was found. |
| **(i) Page-image reader and carry-edits, as she sees them** | Page-image reader: a saved row looks like any other row, except that its source panel shows the page without a box and the sentence quoted in (g); nothing on the row says it was read by a model from the page image. Carry-edits: the queue reason "Your saved corrections were made before Loupe read the PDF again … Compare the saved corrections with what Loupe reads now, shown side by side" (filter "Saved corrections to compare (5)"); on the statement, "The reading changed after this review was saved … Show previous saved values (165 rows)" and the confirmation checkbox. | | The provenance of page-image rows is not visible on the row. |

Console and network (seen): no JavaScript errors from the app itself; server 500 on the main transactions request once (00:48) and again under load; browser-side request aborts after 60 s on the queue; connection refused during each deploy.

## 2.3 Nielsen's 10 heuristics, scored 1-5 from the live screens

| # | Heuristic | Score | Evidence (screen: what happened) |
|---|---|---|---|
| 1 | Visibility of system status | 2 | Queue status line now adds up to a total. But screens show "Loading…" for 30 s to 4 min with no progress; the queue fails with "signal is aborted without reason"; Overview and Statement files status panels fail on every visit; "files have saved statements" prints "…" instead of a number; re-reading paused shows only as "Being rechecked 0". |
| 2 | Match with the real world | 2 | Queue steps are plain ("Open the PDF at page 1. Look for the bank's name or logo"). Elsewhere: "Enter at least one printed opening or closing balance to save a statement without transactions" as a headline; "preparation recovery", "Processing batches", "Not payment statements"; raw database deadlock text on the ledger runs view; internal IDs on the decisions view. |
| 3 | User control and freedom | 3 | Drafts saved before moving; Previous/Next statement with issues; her earlier corrections kept and shown beside the new reading; read-only banner explains the state. Not observed: undo of an import. |
| 4 | Consistency and standards | 1 | 66 accounts / 12 banks (Overview) vs 260 / 14 (Transactions); "Needs (93)" vs "Waiting for you 89"; "Imported 2,197 statements" vs 1,208 periods; the same bank under several spellings; accounts named after files; the queue headline contradicting the statement screen. |
| 5 | Error prevention | 4 | Import disabled until the statement reconciles; page-image rows saved only when proved (6 of 65); read-only users cannot write; 1 audited disagreement out of 651. |
| 6 | Recognition rather than recall | 3 | Each queue item names page and action. Tracing, graph and patterns tools start from empty forms; the analyst has to know which of them answers which question. |
| 7 | Flexibility and efficiency | 2 | "One answer for 2 statements" for currency; Previous/Next held statement. No keyboard flow; rows typed one by one; 30-240 s loads multiply every step. |
| 8 | Aesthetic and minimalist design | 2 | Sticky "To fix" box covers the PDF; filtered views show empty blocks for 146 accounts; long qualifying paragraphs above every table. |
| 9 | Help users recognise, diagnose and recover from errors | 1 | "signal is aborted without reason", "Failed to fetch", raw deadlock text; a headline that sends her to page 12 for unreadable rows when the actual blocker is a checkbox. |
| 10 | Help and documentation | 3 | "Financial guide" button on every financial screen; queue items are self-explaining. The guide's content was not re-read for this audit. |
| | **Average** | **2.3** | |

## 2.4 What the live UI does well (keep)

- The source page with the printed line boxed, two clicks from any payment, for 99.0% of saved payments (seen, measured).
- Queue items written as instructions with the page named, and "Loupe checks it again and imports it by itself" stated on each.
- Reconciliation shown as a checklist on the statement (opening and closing, running-balance intervals, printed totals), each marked matches or not.
- Copies set aside and linked, with the reason recorded.
- Her earlier corrections are kept beside a new reading rather than lost or silently applied.
- Careful wording on flows ("These connections do not establish ownership or show that one receipt funded a later payment").

---

# Part 3. Competitive usability benchmark

Sources: two research passes (2026-10-24, web; full notes and URLs in Appendix A). Labels: **(verified: URL)** a vendor help or documentation page or a third-party page; **(vendor claim)** marketing; **(inferred)** reasoning. Independent reviews barely exist for this category, and no Reddit or ACFE threads surfaced for any tool. **Every Loupe cell below is judged from the live walkthrough and live measurements in Parts 1-2**, not from plans or code.

## 3.1 The tools that matter, in one line each

| Tool | What it is relative to Loupe | Key evidence |
|---|---|---|
| **Valid8** | Closest established investigator product: statements in, reconciled ledger, transfers, Sankey, indexed PDF report | "Verification" is the balance tie-out (green/yellow), not human checking; PDFs go to an external service, FIFO, "no override available to users or to support" (verified: customersuccess.valid8financial.com/knowledge/account-grid-overview, /-how-long-processing-takes). Pricing not published. |
| **Docuritas** | 2026 product aimed at "ledger you can defend": running-balance proof, first mismatched row, gaps/overlaps, examiner edits logged by name, bound exhibit with SHA-256 per file and a findings hash per page | Vendor claim (docuritas.com; legaltechnologyhub.com/vendors/docuritas); USD 999 per matter (verified on page). No reviews. |
| **Altia FIT / Investigator** | UK police standard: OCR re-digitising + analysis toolbar | GBP 4,160-4,690 per licence per year (verified: G-Cloud 14 listing). No review process for OCR output described. |
| **i2 Analyst's Notebook** | Link charts from structured data; no statement extraction | Summed links show count and total value per direction (verified: ibm.com/support/pages/node/716175). |
| **CaseWare IDEA** | Audit analytics; user builds import templates | Learning-curve complaints on G2/TrustRadius; no review queue concept. |
| **DocuClipper** | Low-cost statement converter with reconciliation | Opening + deposits - withdrawals = closing; "edit transactions in place until totals match" (verified: docuclipper.com/features/bank-statement-reconciliation); USD 20.30-279.30 a month (verified: pricing page); unsupported formats added "within 48 hours" (vendor claim). |
| **MoneyThumb** | A failed reconciliation triggers a targeted re-read, then the exact values to check are highlighted | (verified: moneythumb.com/?p=15796; docs.moneythumb.com) |
| **Ocrolus** | Machine pass plus paid human verifiers; lists Mexico | "US, Canada, Mexico, and the United Kingdom" (verified: docs.ocrolus.com/docs/bank-statements); a 2023 incident left 517 documents overdue when human verification slowed (verified: pingoru.io). |
| **Docsumo** | Exceptions-only review with typed error codes | Balance discrepancy, date tally, out-of-period rows, likely-cause rows (verified: support.docsumo.com/docs/bank-statement-review-tips). |
| **Rossum** | Generic document review; best documented keyboard flow | Enter jumps to the next field needing review (verified: knowledge-base.rossum.ai). |
| **Sensible** | Per-bank configs plus LLM, sold with a config-writing service | (vendor claim: sensible.so/doc-types/bank-statements) |
| Hummingbird / Unit21 | AML case queues | Hummingbird one-click case export (verified); Unit21 audit trail omits note and checklist changes (verified: docs.unit21.ai/docs/audit-trails). |
| Palantir, Quantexa, Siren, Nuix, Cellebrite Pathfinder, Penlink | Assume structured data already exists | (verified/inferred, research A §6-11) |

## 3.2 Feature and usability matrix (0-5)

Competitor scores rest mostly on vendor documentation ("?" = no evidence found). Loupe scores are for the live app as walked on 2026-10-25.

| Capability | Loupe (live) | Valid8 | Docuritas | Altia | i2 ANB | IDEA | DocuClipper | MoneyThumb | Ocrolus | Docsumo | Rossum |
|---|---|---|---|---|---|---|---|---|---|---|---|
| (a) Load and see what was read, what wasn't, why | 2 | 4 | 4 | ? | 0 | 1 | 3 | 3 | 3 | 4 | 4 |
| (b) Fix a held statement | 2 | 3 | 3 | ? | 0 | 1 | 3 | 4 | 2 (vendor fixes) | 4 | 5 |
| (c) Duplicates / copies | 4 | 3 | ? | ? | 1 | 2 | ? | 2 | 2 | ? | 3 |
| (d) Account history, gaps | 3 | 5 | 4 | 2 | 1 | 2 | 2 | 2 | 1 | 2 | 0 |
| (e) Follow money | 2 | 4 | 3 | 3 | 5 | 1 | 3 | 1 | 0 | 0 | 0 |
| (f) Search / filter | 4 | 4 | 2 | 3 | 3 | 4 | 2 | 1 | 1 | 1 | 1 |
| (g) Transaction → source page | 5 | 3 | 3 | ? | 0 | 0 | 1 | 1 | 2 | 4 | 4 |
| (h) Annotate and export exhibit | 2 | 4 | 5 | 3 | 4 | 3 | 2 | 1 | 1 | 1 | 1 |
| Coverage, Mexican banks / Spanish | 3 | ? | ? | ? | n/a | 1 | 1 | ? | 2 | 1 | n/a |
| Coverage, unseen layout | 1 | 4 | ? | ? | n/a | 1 | 3 | 3 | 4 | 3 | 3 |
| Speed and stability of the working screens | 1 | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? |
| Speed to a usable ledger | 2 | 3 | 4 | 3 | n/a | 2 | 4 | 4 | 4 | 4 | 4 |
| Trust: wrong values kept out | 5 | 3 | 4 | ? | n/a | 2 | 3 | 3 | 4 | 4 | 3 |
| Trust: audit trail of edits | 4 | 3 | 5 | ? | 3 | 3 | 3 | ? | ? | 4 | 4 |
| Learning curve (5 = easy) | 2 | 3 | 4 | 3 | 2 | 2 | 5 | 4 | 4 | 4 | 4 |

Loupe's cells, justified from the live app, and the row leader:

| Row | Loupe (live evidence) | Leader and why |
|---|---|---|
| (a) | Status line adds up, but two status panels fail every visit, the queue times out, counts disagree across tabs, raw errors on the runs view | Valid8 chevrons All / Unassigned / To Reconcile / Reconciled with counts (verified); Docsumo shows only failures, reason attached (verified) |
| (b) | Numbered steps with page; reconciliation checklist; but a headline can contradict the statement, 19-128 s to open, rows typed one by one | Rossum keyboard flow (verified); MoneyThumb re-read then exact values (verified) |
| (c) | Copies set aside automatically, linked, reason recorded; decisions name documents by internal ID | Loupe leads; no competitor documents an equivalent |
| (d) | Per-account missing months and missing date ranges; no case-wide grid; accounts named after files | Valid8 Account Grid, gaps exported (verified) |
| (e) | Careful flow summaries and four tracing modes, but 86% of payments have no counterparty, including transfers that print the sender | i2 summed links (verified); Valid8 transfer matching and Sankey (verified) |
| (f) | 3.5 s search with totals on exactly the filtered rows, CSV | Loupe and Valid8 level |
| (g) | Boxed printed line two clicks from any payment, 99.0% of saved payments | Loupe leads; Docsumo/Rossum show source during review only |
| (h) | CSV and findings; no exhibit output found; report creation not exercised | Docuritas bound exhibit with page cites and hashes (vendor claim) |
| Coverage MX | 1,208 BNB2 periods across BBVA, Santander, Monex, Intercam, Kapital, Scotiabank; 65% saved with no human action | Loupe leads by default: no researched vendor names these banks |
| Unseen layout | Page-image reader live but proves 6 of 65 held statements so far | Valid8 "template-free" (vendor claim); Ocrolus human verifiers |
| Speed/stability | 30 s-4 min loads, 3 queue time-outs, 6 restarts in two hours | No competitor evidence either way; this row is about Loupe's own bar |
| Trust: wrong out | 650 agree / 1 disagree on the BNB2 audit; page-image rows saved only when proved, 0 wrong | Loupe leads; most competitors equate "verified" with "balance ties" |
| Audit trail | Decisions view: what, who, when, before and after kept | Docuritas edits logged by name inside the exhibit (vendor claim) |
| Learning curve | 7 tabs plus 4 sub-tabs plus a menu of tools; long qualifying text | DocuClipper: almost nothing to learn |

## 3.3 Where Loupe is genuinely better (live, evidenced)

1. **Source traceability on every saved payment.** Two clicks from any row to the printed line boxed on its page (seen); 99.0% of 24,159 saved payments (measured). No researched competitor documents this for saved rows.
2. **Wrong values kept out, measured.** 650 of 651 audited BNB2 periods agree with the answer key; page-image readings are saved only when the arithmetic proves (6 of 65, 0 wrong). Competitors' "verified" generally means the balance ties.
3. **Mexican bank coverage nobody else claims.** 65% of BNB2's statements reached the ledger with no human action (measured).
4. **Copies handled as evidence, not deleted.** 82 copies set aside and linked, each with its reason (seen, measured).
5. **Correction model.** Her earlier corrections are kept beside a new reading and shown side by side (seen).

Not a demonstrated advantage on the live app: speed, coverage of unseen layouts, counterparty identification, a single exhibit.

## 3.4 Where others are better (blunt)

1. **Their working screens load.** Loupe's main screens took 30 s to 4 min and the queue timed out three times in one evening; the app was restarted six times in two hours under her.
2. **Their status is one set of numbers.** Valid8's chevrons are four counts that add up. Loupe shows different account, bank and statement counts on different tabs, and two status panels fail.
3. **They show the holes on one screen.** Valid8's Account Grid. Loupe lists missing months account by account, and some accounts are titled with a file name.
4. **They make a failed statement quick to fix and point at the broken row.** Docsumo, MoneyThumb, Rossum, Docuritas. Loupe's queue headline can name the wrong problem and page, and rows are typed one at a time.
5. **They identify the other party.** Loupe leaves 86% of payments with "Counterparty not identified", including transfers that print the sender's name and account.
6. **Their exhibit is one button.** Docuritas and Valid8 produce an indexed PDF where every transaction cites file and page. Loupe has better source boxes than either but no exhibit output.

## 3.5 The coverage question

**How the leaders get high coverage.** Humans behind the machine (Ocrolus); per-format configuration sold as a fast service (Sensible, DocuClipper's 48 hours); lower precision with a balance check and a fast review screen (DocuClipper, Docsumo, MoneyThumb); a failed balance as a trigger to re-read (MoneyThumb; Reducto's "iterate until it balances", which is dangerous for evidence). Self-reported unattended rates (Heron about 90%, Docsumo and Sensible "95%+") are vendor claims on US lending documents. Nobody credible claims 100%, and nobody documents Mexican bank coverage.

**Where Loupe stands live.** The arithmetic gate is reader-agnostic and is now in use with a second reader: the page-image reader runs on held BNB2 statements and its proved readings go through the same gate (6 saved, 0 wrong). Its holds are mostly rules, not reading failures: 14 pages missing (correctly held), 16 statements with Alex's saved work (not read by design), 4 with no earlier statement to confirm the header against.

**Recommendation.** Make the page-image reader the default second pass for every held statement, including the 16 with her saved work (offered beside her version, never saved over it) and first statements (header accepted when the two readings agree), behind the same gate. Keep the guards it already has: rows marked "read from page image" with page, model never given the target balance, per-row running-balance check where the statement prints one, stored response, approved-case list. Show the reading's origin on the row in the source panel.

**Risks.** On OCR-damaged pages arithmetic is the only verifier, and two compensating errors pass a period total; the running-balance check mitigates this only where balances are printed. Re-runs can differ; store and pin. Case page images go to OpenAI under the approved-case list; zero-data-retention terms should be confirmed for material under protective order. Cost is small (USD 0.11 a statement measured).

---

# Part 4. Prioritised improvement list

## Fix in the next two weeks

| # | Problem | Evidence (live) | Best competitor practice | Proposed change | Effort | Expected impact on Alex |
|---|---|---|---|---|---|---|
| 1 | Main screens take 30 s-4 min; queue times out | Part 2, Appendix D | Valid8/Docsumo dashboards (vendor docs) | Profile and cache the six slow requests (evidence list, ledger, statement-import files, account parties, transactions, queue); target under 5 s each on BNB2 | M | Every task becomes possible in one sitting |
| 2 | The app restarts under her | 6 deploys in two hours, each showing "Failed to fetch" | n/a | One daily deploy window outside her hours, batching every passed unit; a "Loupe is updating, back in N minutes" banner instead of fetch errors | S | No lost screens or drafts mid-task |
| 3 | Two status panels fail every visit; "…" instead of a number | Overview "Your statements"; Statement files "import status" | Valid8 chevrons | Fix the failing status request; show one set of counts | S | She can see what is done |
| 4 | Counts disagree across tabs | 66/12 vs 260/14; 93 vs 89; 2,197 vs 1,208 | Valid8 four counts that add up | One definition each for account, bank and statement; merge bank spellings; name accounts by holder, bank and number, never a file name | M | She can state the case's scope and defend it |
| 5 | Queue headline can contradict the statement | "rows could not be read on page 12" on a statement whose every check matches; opens on page 1 | Docsumo typed error codes; Docuritas first mismatched row | Derive the headline and page from the blocking check shown on the statement; open the PDF on that page | S | She goes straight to the real problem |
| 6 | Raw errors on screen | "signal is aborted without reason"; psycopg deadlock text on runs view; internal IDs on decisions | n/a | Plain messages with what to do; hide runs that broke and were superseded; name documents by account and period | S | Fewer dead ends |
| 7 | Re-reading paused, so carry-edits does nothing | "Being rechecked 0"; sim: 71 → 35 refused for her work | Docsumo re-runs checks after edit | Resume re-preparation (decision 1) | S | The waiting count can fall again |
| 8 | Page-image reader skips the statements that need it most | 16 with her saved work, 9 first statements, 62 not offered at 01:15 | MoneyThumb re-read on failure | Decisions 3 and 4; offer every held statement | M | The largest remaining lever on the 107 |

## Structural

| # | Problem | Evidence (live) | Best competitor practice | Proposed change | Effort | Expected impact on Alex |
|---|---|---|---|---|---|---|
| 9 | 86% of payments have no counterparty | 20,802 of 24,159; transfers print sender name and account | i2 summed links; Valid8 transfer matching | Read sender and beneficiary from SPEI and transfer descriptions; match own-account transfers across the case | M | Follow money starts working on her case |
| 10 | No case-wide coverage view | Missing months listed per account | Valid8 Account Grid with gap export | Account × month grid for the whole case; export missing periods as a list | M | Holes in the evidence at a glance |
| 11 | Fixing a held statement is slow | Field by field; rows typed one at a time; sticky box covers the PDF | Rossum keyboard flow; Docsumo exceptions-only | Page-first review: failing rows highlighted, Enter for next problem, totals re-checked on every edit, page-image rows proposed for confirmation | L | Minutes per statement |
| 12 | No exhibit output | CSV and findings only | Docuritas bound exhibit; Valid8 indexed PDF | "Exhibit for this account / period / finding": indexed PDF with page citation and boxed thumbnail per transaction, file hashes, list of hand corrections | M | Court-ready output from what Loupe already knows |
| 13 | Too many entry points | 7 tabs, 4 sub-tabs, a menu of tools that each start from an empty form | Valid8 Load → Confirm → Match → Analyse | Re-cut around four jobs: get the statements in, make the ledger right, follow the money, report | M-L | Less to learn |

---

# Appendix

## A. Sources

Live (this assessment, 2026-10-25 00:40-02:55 UTC): the logged-in walkthrough (Part 2, Appendix C); read-only database queries (Appendix B); `services.financial.review_queue` counts via the live queue function; `/mnt/owl-data/fin-real/audit-replace/ledger-audit.json` (live ledger audit, 01:20 UTC).

Run logs: `/mnt/owl-data/fin-wt/headless/STATUS-FOR-NEIL.md` (02:25 version); `/mnt/owl-data/fin-wt/headless/real/ALEX-QUEUE-WORK.md` (lines to 02:42); `deploy/logs/.last-good-commit` and `deploy/logs/deploy-20261025-*.log`; `/mnt/owl-data/fin-wt/notes/r7-alex-queue-explainer.md` (trend point).

External: full notes with every URL and label in `/mnt/owl-data/fin-wt/headless/fin-assess-research-A.md` (forensic and investigator tools) and `fin-assess-research-B.md` (extraction tools). Key URLs: customersuccess.valid8financial.com/knowledge/account-grid-overview; customersuccess.valid8financial.com/knowledge/-how-long-processing-takes; docuritas.com; legaltechnologyhub.com/vendors/docuritas; applytosupply.digitalmarketplace.service.gov.uk/g-cloud/services/148862043335266; ibm.com/support/pages/node/716175; docuclipper.com/features/bank-statement-reconciliation; docuclipper.com/pricing; moneythumb.com/?p=15796; docs.ocrolus.com/docs/bank-statements; pingoru.io/providers/ocrolus/incidents/2245729; support.docsumo.com/docs/bank-statement-review-tips; knowledge-base.rossum.ai/docs/document-validation-screen-in-rossum; sensible.so/doc-types/bank-statements; docs.unit21.ai/docs/audit-trails.

## B. Method and safety

- **Login:** a view-only guest user, member of BNB2 with case view permission only. The read-only banner appears on every financial screen.
- **Browser:** Playwright with headless Chromium 1228 against `http://10.142.0.5:5174`, viewport 1600×1000. In every browser context a route handler **aborted every request that was not GET, HEAD or OPTIONS**, except `POST /api/auth/login` and two endpoints the statement screen needs to render: `POST /api/financial/statement-import/{file}/checks` and `/coverage-check`. Those two were allowed only after checking the router (request-scoped session, closed without commit) and running the same functions inside a `SET TRANSACTION READ ONLY` transaction, which completed without error. No other request was allowed; no other blocked request was seen. No save, approve, import, re-read, delete or confirm button was clicked.
- **Database:** `SET TRANSACTION READ ONLY`, asserted `transaction_read_only = on`, rolled back. Queries: current admitted periods by who started the ingestion run; period dates and reconciliation status; saved payments by ledger status and source locator kind; page-image reader records per file; ingestion runs by status.
- **Queue counts:** `review_queue._compute` and `case_review_queue(use_cache=False)` in read-only transactions (02:45 UTC).
- **Coverage definitions:** as in 1.2.

## C. Screenshots (kept outside git: `/mnt/owl-data/fin-wt/fin-assess-shots-live/`, they contain case data)

| File | Screen |
|---|---|
| 02-financial-overview.png | Overview after a 104 s load |
| w1-statements.png | Review queue with status line and filters |
| w3-02.png | Held statement opened from the queue ("To fix" box, Statement 8 of 50) |
| w3-03.png | Same statement scrolled: sticky box over the PDF, import disabled, "Issues and edits" |
| w4-01.png, w5-*.png | Transactions search (82 results) and expanded details |
| w6-04.png | Payment detail with the source page and the printed line boxed |
| w7-*.png | Overview, People & businesses, Follow money, Findings, ledger runs (raw errors), tracing, transfers, graph, decisions, patterns, case context |
| w8-02..06.png | "Nothing could be read" filter, Statement files, Processing batches, Review accounts, Reports |
| w9-03.png | A payment read from page images (page shown without a box) |

## D. Timings and restarts (seen)

| Screen | Load to settled (seconds), each attempt |
|---|---|
| Login | 1.8-4.9 |
| Financial Overview (cold) | 104, 35 |
| Statements & accounts / queue (cold) | 91, 218, 242, 120, 100, 112, 89, 56, 75 |
| Open a held statement from the queue | 128, 19 |
| Transactions (after another tab) | 70 |
| People & businesses | 18, 137 |
| Follow money | 21, 38 |
| Review accounts | 84 |
| Statement files | 36 |
| Search within Transactions | 3.5 |
| Open a payment's source page | 3.4 |

Slowest requests in one cold load: statement-import files 109 s, transactions 105 s, workspace entries 100 s, case 99 s, ledger 99 s, account parties 104 s (People & businesses). The queue request is abandoned by the browser at 60 s ("signal is aborted without reason"), seen three times.

Live deploys during the walk: `dbf9e14e` attempts from 00:50 (frontend stopped on each), `f257abb9` 01:03, `1f762cc7` about 01:20, `682ce6bb` about 01:55, `f81d5aff` 02:21, `f81d5aff` again 02:46. Each showed the open session "Failed to fetch", "Transactions could not be loaded. Refresh this page to try again" or connection refused.

## E. Limits

- The walkthrough user is read-only, so saving, importing and report creation were walked to the button and not performed; times for those steps are not measured.
- The host was also running build and recovery work (load average 5-9); Alex's own sessions may see different times. The times are what the live app delivered on 2026-10-25, not a lab measurement.
- Field and row counts for held statements are taken from the queue's own item text on its first page (47 of the waiting items at 00:50).
- Competitor scores are judgements from vendor documentation, not hands-on trials; "?" means no evidence found.
- Bench and simulation figures are quoted from the run logs, not re-run (no benches by instruction).
