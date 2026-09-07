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
