# Local application testing

This stack is for synthetic data. It uses separate Docker volumes and loopback
ports, leaving the existing Owl containers and evidence directories untouched.
The backend and evidence engine use separate Python 3.12 virtual environments.

From the repository root, install once:

```sh
python3.12 -m venv data/local-runtime/backend-venv
data/local-runtime/backend-venv/bin/python -m pip install -r backend/requirements.txt
python3.12 -m venv data/local-runtime/engine-venv
data/local-runtime/engine-venv/bin/python -m pip install -e ./evidence-engine
```

Install frontend dependencies with `npm ci --ignore-scripts` in `frontend_v2`.
Docker, Node, ffmpeg, Tesseract (English and OSD), and the native libraries needed
by WeasyPrint must be installed. On this Mac they are already available; the
launcher adds Homebrew's library directories for PDF rendering.

Start services and migrate the isolated database:

```sh
docker compose -f docker-compose.local.yml up -d
python3.12 scripts/local_app.py migrate
```

Wait for PostgreSQL to be healthy before migrating. Then run each command in its
own terminal, leaving it running:

```sh
python3.12 scripts/local_app.py backend
python3.12 scripts/local_app.py engine
python3.12 scripts/local_app.py worker
python3.12 scripts/local_app.py frontend
```

Open <http://127.0.0.1:55174>. The API is on port 58002 and evidence API on
58003. Docker services: PostgreSQL 55434, Neo4j HTTP 57474 / Bolt 57687,
Redis 56379, Chroma 58101. Runtime files and venvs are ignored under
`data/local-runtime`; databases persist in the `loupe-local` Docker volumes.

The launcher overrides database/storage/auth settings and disables loading the
repository `.env`. It uses a deliberately invalid OpenAI key and clears other
provider credentials. **AI extraction, embedding, chat and transcription are not
validated.** The engine's existing `openai` health check only tests whether a key
is nonempty; `ready` does not prove provider access. Do not put real evidence into
this development stack or treat its published development credentials as secure.

Run the real HTTP/PostgreSQL duplicate check after startup:

```sh
PYTHON_DOTENV_DISABLED=1 data/local-runtime/backend-venv/bin/python scripts/check_local_duplicates.py
```

On an empty installation this creates the local administrator:
`loupe-local@example.com` / `Loupe-local-test-2026`. It leaves a labelled synthetic
case for inspection. Each invocation creates another case. It checks simultaneous
HTTP exclusion, restoration, and two separate PostgreSQL writers demonstrably
waiting on row locks, with exactly one successful exclusion. No test database
target is configurable, and the check does not erase data.

Stop the four native processes with Ctrl-C in their terminals. Stop Docker
services with `docker compose -f docker-compose.local.yml stop`; data is retained.

Check read-only source amount assessment through HTTP and PostgreSQL:

```sh
PYTHON_DOTENV_DISABLED=1 data/local-runtime/backend-venv/bin/python scripts/check_local_source_amounts.py
```

Run the duplicate check first on a fresh installation to create the local tester.
The source check leaves a labelled synthetic case and three generated text files
with digital, recognized and unknown provenance. It verifies exact readings,
wrong-case and stale-source refusal, and absence of ledger/adjudication writes.
Its case/file IDs are saved in `data/local-runtime/source-amount-check.json`.
In that case's Evidence view, switch Search scope to “Text in case”, search for
“Synthetic amount review”, and open “Assess an amount in source text”. Select
1234 and enter USD. Digital text returns 1234.00; the other sources offer 12.34
and 1234.00. These are synthetic provenance fixtures, not an extraction test.

Check ledger-to-PDF navigation with a generated source and stored rectangles:

```sh
PYTHON_DOTENV_DISABLED=1 data/local-runtime/backend-venv/bin/python scripts/check_local_ledger_source.py
```

This creates another labelled synthetic case, with one admitted row and one held
out. It checks both citation endpoints, the rendered PNG and original PDF digest.
Open the returned case's Financial view and use View source on each tab. The
stored rectangle identifies the corresponding printed amount; Open source file
opens the original PDF. Fixture IDs persist in
`data/local-runtime/ledger-source-check.json`. The fixture assigns positions
explicitly and does not test automatic extraction or admission. Backend
requirements now include PyMuPDF; an older venv needs that dependency installed
to serve page images.

Pass `--correct-held-out` to the ledger source check to also record a synthetic
20.00 → 21.00 GBP correction. In Decisions, expand Original and replacement
readings and open each source. Both retain the original PDF rectangle; the old
row is superseded and the replacement remains held out. This deliberately altered
fixture validates history/navigation, not the correctness of the replacement.

Verified 6 September 2026: migrations from an empty PostgreSQL database to head,
all service connections and OCR, native PDF rendering, both venvs' `pip check`,
3,497 financial tests (12 skipped), and the real duplicate/lock-contention check.
This is a working integration environment, not exhaustive application acceptance
testing. The dependency ranges and image major tags are not a complete frozen
release lock.

Check pending PDF candidate storage and real PostgreSQL contention:

```sh
python3 scripts/local_app.py migrate
PYTHON_DOTENV_DISABLED=1 data/local-runtime/backend-venv/bin/python scripts/check_local_candidates.py
```

This generates a labelled PDF/case and reads its actual table geometry. Two writers
are held at a PostgreSQL source-row lock before release; exactly one mapping and
two pending originals survive, and neither enters the ledger. Direct SQL attempts
to UPDATE either original table are refused by database triggers. The script uses
only the isolated local database and records IDs in
`data/local-runtime/candidate-check.json`. The script also verifies authenticated mapping reads and original amount
assessment through the local backend. Authenticated creation retries also return the same saved originals. The migration refuses downgrade while saved originals exist.

Check append-only candidate reviews and stale-review contention:

```sh
PYTHON_DOTENV_DISABLED=1 data/local-runtime/backend-venv/bin/python scripts/check_local_candidate_reviews.py
```

This creates a fresh synthetic candidate case, then holds two reviewers at a
PostgreSQL lock and verifies one success/one stale-revision refusal. Normal login
and HTTP then reopen and resolve the reading, retaining three history entries and
the original text. A database trigger refuses history updates. Fixture IDs persist
in `data/local-runtime/candidate-review-check.json`. The deliberately reviewed
12.34 GBP differs from the original digital reading 1234.00 GBP; it tests audit
preservation, not the truth of that correction. Resolution does not admit a ledger
transaction. Saved candidate review is available under Financial → Ledger → PDF readings.


Check the actual candidate review screen with Chromium (frontend and backend running):

```sh
node scripts/check_local_candidate_ui.cjs
```

Run the review fixture script above first. This UI check signs in normally, opens
the saved synthetic PDF readings, reopens/resolves a reading, verifies the original
1234.00 GBP assessment and source page image, and saves the exact reviewed 12.34 GBP
with retained history. A screenshot is saved to
`/tmp/loupe-neilbyrne-candidate-review-ui.png`. It changes only that labelled test
case. The screen supports rejection, review reload, account search and all three
date roles. A stable accessible label is used for selects and the reason textarea.
Source mapping creation still requires the API or fixture script; automatic PDF
import, account creation and ledger materialization are not part of this screen.


Select and save rows from stored PDF tables in Financial → Ledger → PDF readings
→ Choose PDF rows. Pick a source page/table, inspect its image, assign column
meanings and select rows. Nothing is selected or classified automatically. Reload
resets the selection; identical saves return the same mapping. New extraction and
account setup remain separate prerequisites. Verify this with a synthetic case:

```sh
PYTHON_DOTENV_DISABLED=1 data/local-runtime/backend-venv/bin/python scripts/check_local_candidates.py
node scripts/check_local_candidate_source_ui.cjs
```

The browser check selects only one row, checks the source image, saves twice and
verifies the same mapping ID with one pending candidate. IDs are recorded in
`data/local-runtime/candidate-source-ui-check.json`. To run a read-only contract
check on the user-provided PDFs without inserting them into any database:

```sh
PYTHON_DOTENV_DISABLED=1 data/local-runtime/backend-venv/bin/python scripts/check_real_pdf_candidate_sources.py
```

This uses same-pass extraction snapshots in memory, binds all extracted nonempty
rows with unknown meanings and writes only aggregate diagnostics under
`data/local-runtime/pdf-inspection`. It does not classify those rows as transactions
or constitute real-document ingestion acceptance. Real PDFs and generated page
images stay outside Git. Both supplied files passed: 153 tables/7,529 source rows
across 164 pages, including 11 verified blank pages.


A candidate review can now create a **provisional account** when no identified
account is available. Supply currency, a descriptive label and a reason. The label
is investigator context, not a printed identifier or holder name. Its identity
stays separate by source file/currency/label; another source cannot use it. Known
account identification/merging remains separate work. Creation records an ingestion
run and does not resolve the candidate or admit money. Repeatable local checks:

```sh
PYTHON_DOTENV_DISABLED=1 data/local-runtime/backend-venv/bin/python scripts/check_local_candidate_accounts.py
node scripts/check_local_candidate_account_ui.cjs
```

Both use the synthetic case IDs from `candidate-check.json`. The first proves two
creators waiting on a PostgreSQL lock produce one account, checks authenticated
retry and unchanged review/totals, and writes `candidate-account-check.json`. The
second creates/selects an account through the browser and resolves a synthetic
12.34 GBP reading; its source stays unchanged and no transaction enters totals.
Screenshot: `/tmp/loupe-neilbyrne-provisional-account-ui.png`.


Saved PDF batches also expose **Check repeated source rows**. It compares pending
and resolved candidates across that PDF's mappings and links to the exact readings.
Rejected candidates remain counted. The check detects reused grid rows/overlapping
text and possible overlapping source areas; equal amounts alone are not duplicates.
Uncomparable mixed or unlocated sources and comparison/detail limits are explicit.
This is a snapshot check, not a transaction deduplicator or ledger-write permit.

After running the synthetic source-selection check (which adds a second mapping
that reuses one original row), verify the read-only browser check with:

```sh
node scripts/check_local_candidate_reuse_ui.cjs
```

It expects at least one reused source row, verifies reported comparison coverage
and follows the finding to its exact candidate. Screenshot:
`/tmp/loupe-neilbyrne-source-reuse-ui.png`. It makes no review or ledger changes.


Run notices and the Attempts table distinguish provisional-account setup from
transaction import. Failed/refused setup remains visible with its recorded error,
but does not claim missing imported transactions. Mixed histories retain the real
import warning and count setup separately. An operation label contradicting nonzero
import counters does not suppress an import warning.

## Finalized PDF readings and later corrections

Run these in order against the isolated services with the current backend. They
create a fresh synthetic PDF case, resolve its two rows, finalize them through the
browser, then correct one ledger amount while retaining its original source:

```sh
PYTHON_DOTENV_DISABLED=1 data/local-runtime/backend-venv/bin/python scripts/prepare_local_finalization_ui.py
node scripts/check_local_finalization_ui.cjs
node scripts/check_local_finalized_review_ui.cjs
```

The last script requires a freshly finalized fixture without a previous correction;
rerun all three to repeat the complete check. It verifies the read-only candidate
screen, retained history and source assessment, an authenticated 409 for provisional
account setup after finalization, a GBP12.34→12.35 ledger replacement remaining P3,
and the original receipt's correction notice and highlighted PDF row. Results are
in `data/local-runtime/finalized-review-ui-check.json`. Real evidence is not used.

Saved candidate review also offers **Assess original dates**. This read-only check
shows possible numeric calendar readings and missing year/century/context beside
the original PDF cell. It never fills the review fields or repairs OCR characters.
With a synthetic fixture from check_local_candidates.py, including one already
finalized, verify the missing-year alternatives and source highlight with:

```sh
node scripts/check_local_candidate_dates_ui.cjs
```

The script uses candidate-check.json and leaves reviews and ledger money unchanged.
It expects the synthetic first-row date `01/02`. Screenshot:
`/tmp/loupe-neilbyrne-candidate-dates-ui.png`.

The source picker offers **Suggest column meanings** for exact labels in its first
ten stored rows. Suggestions require an explicit click and never select rows.
Generic Date remains unresolved; Transaction date is now a separate supported role
in both grid and canonical-text mappings. To test against a fresh synthetic PDF:

```sh
PYTHON_DOTENV_DISABLED=1 data/local-runtime/backend-venv/bin/python scripts/prepare_local_header_ui.py
node scripts/check_local_header_ui.cjs
```

This uses a separate header-check.json fixture. The browser accepts two printed
labels, selects only one non-header row, saves it pending, and verifies an identical
retry preserves its mapping. Results: header-ui-check.json; screenshot:
`/tmp/loupe-neilbyrne-header-suggestions-ui.png`. No real evidence is used.

## Running-balance impact during correction

Correction previews now show conditional comparisons in source row order and its
reverse. Printed post-transaction balances must still be confirmed against the
source; neither interpretation promotes a proof class. Missing anchors, excluded
rows and unchecked tails are explicit. Mismatches link back to original ledger
sources. Recordings preserve the comparison in the correction audit event.

```sh
PYTHON_DOTENV_DISABLED=1 data/local-runtime/backend-venv/bin/python scripts/prepare_local_running_balance_ui.py
node scripts/check_local_running_balance_ui.cjs
```

These create a fresh isolated synthetic PDF/ledger case, preview GBP400→410 against
printed balances400/420, record the correction remainingP3, and open the original
PDF source. Rerun the preparation before repeating. Reports are running-balance-check.json
and running-balance-ui-check.json under data/local-runtime; screenshots use the
/tmp/loupe-neilbyrne-running-balance prefix. Native controls remain unrevalidated.

## Statement date coverage

The Ledger tab offers **Check statement coverage**. It pages through25 accounts,
with a hard500-period limit per account. Exceeding that limit returns unavailable
rather than showing partial coverage. Only admitted sources with printed start/end
bounds contribute. Dates derived from transactions, missing bounds and excluded
sources remain listed with reasons. Currency groups stay separate.

Overlapping/enclosing periods are combined before finding internal gaps, so an
export spanning a missing month prevents a false date-range gap. Coverage describes
recorded statement bounds, not complete extraction or absence of transactions.
No inference is made about records before/after the first/last known bounds.

```sh
PYTHON_DOTENV_DISABLED=1 data/local-runtime/backend-venv/bin/python scripts/prepare_local_coverage_ui.py
node scripts/check_local_coverage_ui.cjs
```

The synthetic accounts demonstrate a28-day February gap and an enclosing export
that fills it. Reports: coverage-check.json and coverage-ui-check.json under
data/local-runtime. Screenshot: `/tmp/loupe-neilbyrne-statement-coverage-ui.png`.
The synthetic preparation completes its audit run and never uses real evidence.

The Decisions tab now displays the saved running-balance comparison within
**Original and replacement readings**. It is labelled as the result at correction
time, not a recalculation against later ledger changes. Older corrections without
that diagnostic say so. Optional malformed diagnostics do not hide the two readings.
Using the completed synthetic running-balance correction above, verify read-only
history/source navigation with:

```sh
node scripts/check_local_balance_history_ui.cjs
```

Screenshots use `/tmp/loupe-neilbyrne-balance-history-ui.png` and
`/tmp/loupe-neilbyrne-balance-history-source-ui.png`. The check does not edit records.

## Account and date filters on current ledger rows

In Ledger, use **Find accounts**, explicitly select a result, enter optional
ordering-date bounds, and choose **Apply ledger filters**. Typing or selecting
only changes the draft; the scope above the rows describes the applied answer.
Both endpoints are inclusive. **Clear ledger filters** restores all admitted
ledger rows. Case changes reset drafts, applied filters and source/correction
selection. Held out retains its separate behavior.

Account results are bounded to100 with an explicit narrow-search notice. Empty
results do not establish absence of transactions or complete records. Quantified
coverage for the requested account/date interval remains a separate next step.
Using the existing synthetic coverage fixture, this read-only check selects its
February-gap account, verifies an empty February answer, and clears back to10 rows:

```sh
node scripts/check_local_ledger_filters_ui.cjs
```

Report: `data/local-runtime/ledger-filters-ui-check.json`. Screenshot:
`/tmp/loupe-neilbyrne-ledger-filters-ui.png`. No evidence or ledger rows are changed.

Requested-date coverage is available through the case:view read endpoint
`/api/financial/requested-statement-coverage`, requiring case_id, account_id,
start_date and end_date. It intersects eligible printed periods with the inclusive
requested interval, including uncovered dates outside all known bounds. Currency
groups remain separate; missing/derived/excluded bounds and original source-period
IDs remain visible. No eligible bounds or more than500 periods means unavailable,
not a claim of complete evidence. The filter-screen result panel remains next.

```sh
PYTHON_DOTENV_DISABLED=1 data/local-runtime/backend-venv/bin/python scripts/check_local_requested_coverage.py
```

This read-only check uses the existing synthetic coverage fixture to compare a
February gap against an enclosing export, and checks unauthenticated refusal,
missing account and reversed dates. Report: `data/local-runtime/requested-coverage-check.json`.

The applied-filter panel now offers **Check filtered coverage** once one account
and both dates are applied. It shows covered/uncovered requested days separately
for each currency, original period identifiers and excluded bounds. Changing the
applied scope or clearing filters removes the prior result; refresh hides stale
results while checking. No eligible bounds remains unknown, and full printed-date
coverage does not certify complete transactions.

`check_local_ledger_filters_ui.cjs` now also checks February coverage for both
synthetic accounts (0 versus28 covered days) and verifies Clear removes the old
coverage. Screenshot: `/tmp/loupe-neilbyrne-filtered-coverage-ui.png`.

## Exact ledger summary service

`/api/financial/ledger-summary` is a case:view read with optional account_id and
inclusive ordering-date start_date/end_date filters. It returns exact decimal
integer strings for credits_minor, debits_minor and net_minor, separated by
currency. Both row and source must be admitted and in the default counted proof
classes (P0/P1/P2). Other rows are counted once by exclusion reason, in priority
order: row status, source status, then proof classification. Inconsistent ownership
or admitted replacement links refuse the result. More than10,000 matching rows
returns unavailable with null counts and no partial money. This is account-posting
arithmetic; it does not match transfers, establish a balance, or certify completeness.
The display and replacement of existing graph-derived analysis remain next.

```sh
PYTHON_DOTENV_DISABLED=1 data/local-runtime/backend-venv/bin/python scripts/check_local_ledger_summary.py
```

The read-only synthetic check verifies10 postings/GBP2100, an account filter/GBP840,
and an empty February scope. Report: `data/local-runtime/ledger-summary-check.json`.

Ledger now displays **Current ledger summary** for the applied account/date scope.
It preserves exact money strings, shows included classifications and disjoint
exclusion counts, and hides prior totals during refresh or a scope change. Empty
eligible results and unavailable summaries have different messages. Corrections
and row decisions invalidate the same case-scoped query prefix.

```sh
node scripts/check_local_summary_panel_ui.cjs
```

This check sets aside one row in the synthetic coverage fixture and immediately
restores it through the UI. It verifies9 included/1 excluded then10 included and
GBP2100 after restoration. It adds two synthetic audit decisions; it does not use
real evidence. Report: `data/local-runtime/summary-panel-ui-check.json`; screenshot:
`/tmp/loupe-neilbyrne-summary-panel-ui.png`. The graph analysis cards remain legacy.

## Exact money on individual ledger rows

The ledger API now serializes amount_minor and non-null running_balance_minor as
integer strings, preserving the full PostgreSQL bigint range in browsers. Internal
Python views retain integers. Frontend formatting accepts canonical integer strings
and safe legacy numbers; unsafe numeric or malformed values remain unscaled.
External API consumers must accept the string representation for these two fields.

```sh
PYTHON_DOTENV_DISABLED=1 data/local-runtime/backend-venv/bin/python scripts/prepare_local_exact_rows.py
node scripts/check_local_exact_rows_ui.cjs
```

Creates a separate synthetic case and checks9007199254740993 minor units and
-9223372036854775808 running-balance minor units through HTTP, table and decision
dialog (cancelled without a decision). Reports: exact-rows-check.json and
exact-rows-ui-check.json under data/local-runtime. Screenshot:
`/tmp/loupe-neilbyrne-exact-rows-ui.png`.

## Date-grouped authoritative ledger totals

`/api/financial/ledger-trends` accepts the summary's case/account/date scope plus
`grouping=daily|monthly`. It uses the same eligibility pass and exact arithmetic
as ledger-summary, returning the overall totals and date/currency points from one
read. Dates use ordering_date; monthly labels use the first of the month. Points
retain transaction IDs and source-document IDs. Excluded rows do not contribute.
Missing dates are not filled with zero; these totals do not establish inactivity,
balances or deduplicated money movement. The same10,000-row bound applies.
The ledger trends display and navigation to contributing rows remain next.

```sh
PYTHON_DOTENV_DISABLED=1 data/local-runtime/backend-venv/bin/python scripts/check_local_ledger_trends.py
```

Read-only against the synthetic coverage fixture: daily/monthly GBP2100, ten
transaction IDs/five source IDs, and empty February. All fixture postings have
January ordering dates despite their different statement bounds. Report:
`data/local-runtime/ledger-trends-check.json`.

Ledger now offers **Read ledger date totals**, with daily/monthly selection and
25-point pages. Each point offers pages of25 contributing-reading links using the
existing source dialog. Date money reconciles to the overall summary; inconsistent
scope, repeated IDs or mismatched totals are refused. Applied scope changes clear
prior results and source selection. This is a ledger panel; legacy graph Trends
remains separate.

```sh
node scripts/check_local_trends_panel_ui.cjs
```

Read-only check: synthetic daily/monthly GBP2100 and source citation navigation.
The fixture has no stored page rectangle; this check verifies the cited record,
not PDF highlighting. Report: `data/local-runtime/trends-panel-ui-check.json`;
screenshot: `/tmp/loupe-neilbyrne-trends-source-ui.png`.

## Top-level Trends workflow

The main **Trends** tab now uses **Ledger postings** analysis for documentary
transactions: its own applied account/date filters, coverage, exact summary and
daily/monthly totals/source links. It remains available while graph reads are
loading or empty. **Financial intelligence** retains the separate graph-based
claims/valuations view with an explicit limitation; its selector remains accessible
when empty. Graph Transactions and Counterparties are not yet migrated.

`check_local_trends_panel_ui.cjs` now enters the top-level Trends tab to verify
this workflow against the existing synthetic fixture.

## Internal ledger snapshot foundation

`capture_ledger_snapshot` captures source metadata, exact ledger readings,
exclusion reasons and totals from one bounded eligibility SELECT. It serializes
canonical UTF-8 JSON into an immutable value with SHA-256 and byte count. No clock
value is inserted into the content, so unchanged inputs produce unchanged bytes.
Original provenance and superseded/rejected/held-out readings within scope remain.
Source hashes are recorded ingestion hashes, not reverified file bytes.

This service is not exposed as a downloadable export: its content explicitly says
export_ready=false and history_captured=false. Decision-history capture under a
consistent database snapshot, export manifest and UI remain required next.

## Consistent ledger export service

`capture_ledger_export` owns a fresh PostgreSQL REPEATABLE READ, READ ONLY
transaction for rows/totals and relevant decision history. It refuses a reused
connection or non-PostgreSQL engine. History includes captured transaction,
source-document, statement-period and evidence-file subjects within the same case;
actor/reason/before/after and per-subject sequence are preserved. It is not all case
history, and structured candidate-review history is not embedded (provenance and
finalization references remain). Recorded source hashes are not fresh byte checks.

Content schema2 is deterministic; the separate manifest identifies its exact UTF-8
JSON digest, byte count, generation time and code version. More than10,000 decisions
or16 MiB serialized content refuses the export rather than truncating it. HTTP/UI
download is not connected yet.

```sh
PYTHON_DOTENV_DISABLED=1 data/local-runtime/backend-venv/bin/python scripts/check_local_ledger_export.py
```

This synthetic PostgreSQL test excludes a row on another connection between the
export's two reads, verifies the original snapshot remains unchanged, observes the
new decision in a later export, and restores the row in finally. Two synthetic audit
events remain. It verifies digest/byte count and oversize refusal. Report:
`data/local-runtime/ledger-export-check.json`.
