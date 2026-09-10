# Run and check Loupe locally

The Python backend and evidence engine each run in their own virtual environment;
the frontend runs with Node. Local databases use separate Docker volumes and
loopback ports. This is the isolated development stack used for the synthetic
cases and Neil's approved redacted PDF copies. It does not use the deployed
server's databases or provider credentials.

## First installation

Requirements: Python3.12, Node/npm, Docker Compose, ffmpeg, Tesseract with English
and OSD language data, and WeasyPrint's native libraries. On the current Mac these
are installed. Run from the repository root:

```sh
python3.12 -m venv data/local-runtime/backend-venv
data/local-runtime/backend-venv/bin/python -m pip install -r backend/requirements.txt
python3.12 -m venv data/local-runtime/engine-venv
data/local-runtime/engine-venv/bin/python -m pip install -e ./evidence-engine
```

In `frontend_v2`, run `npm ci --ignore-scripts`, then return to the repository root.
These installation commands are not needed every time you start the application.

## Start the application

```sh
docker compose -f docker-compose.local.yml up -d
python3 scripts/local_app.py migrate
```

Wait for PostgreSQL to become healthy before migrating. If a first migration
attempt reports a connection failure, wait and rerun it. Run each of the following
in its own terminal and leave it running:

```sh
python3 scripts/local_app.py backend
python3 scripts/local_app.py engine
python3 scripts/local_app.py worker
python3 scripts/local_app.py frontend
```

Once the backend is running, this creates the local tester on an empty database,
or verifies the existing tester without creating another user or case:

```sh
python3 scripts/local_app.py setup
```

Open [Loupe locally](http://127.0.0.1:55174). Login:
`loupe-local@example.com` / `Loupe-local-test-2026`.
These are deliberately public development credentials for this loopback stack.

## Check it without changing a case

```sh
python3 scripts/local_app.py check
```

This checks the frontend, backend, graph, engine, local OCR, storage, Redis,
worker heartbeat, current database migration head and login. A worker heartbeat
is an availability signal, not proof that a job will finish. Failures return a
nonzero exit code. Results are saved to `data/local-runtime/local-check.latest.json`.
A check without a case does not claim to have tested financial workflows.

To include a case, copy its UUID from the case URL:

```sh
python3 scripts/local_app.py check --case-id e8ecc646-7b29-49d6-b64d-7086a9a14ad4
```

That UUID is the saved real-statement review case on Neil's current local database;
it will not exist on a fresh installation. The case check reads working totals,
statement checks/coverage, the posting graph, transfer candidates, chronology,
patterns and party links. It compares the captured export with working totals
and verifies snapshot/report hashes. It does not create a case, import a file,
change a reading, save a decision or run an external model. A changing case can
legitimately fail the comparison because the separate requests observed different
states; rerun once editing has stopped.

## Current review case

[Open the reviewed statement](http://127.0.0.1:55174/cases/e8ecc646-7b29-49d6-b64d-7086a9a14ad4/financial).
The first printed statement from the108-page PDF contains three reviewed entries:
180USDpayment,61.62USDpurchase and56.16USDinterest. Its owed balance reconciles
from6700.18 to6637.96. This does not claim that all108pages have been finalised.

1. **Ledger:** inspect the three current readings, open their sources and review
   original/correction history. Try theUSD60–70amount range; it selects the61.62
   purchase. Export the table view to retain that range and its contributing row.
2. **Statements:** check balance identity, printed totals where captured, source
   controls and recorded coverage. Native bank-file sources also offer a fresh
   whole-source control check. Download the displayed check page to retain its
   exact results and time. A balanced selected statement does not establish that
   every transaction in the file was extracted.
3. **PDF readings:** choose source pages, scan page ranges, inspect dated and
   undated charge suggestions, and review saved originals beside the PDF. The
   known purchase interest is page3, displayed row22. Do not finalise another copy
   of this statement just to inspect the existing completed example.
4. **Analysis:** compare Transactions, Counterparties, Trends and Posting graph.
   Working figures include admittedP3readings with visible limitations. Verified
   figures excludeP3; zero verified totals here are intentional. Reading review
   and arithmetic agreement do not automatically promote proof class.
5. **Transfers/Patterns:** inspect source-linked candidates and explicit
   assumptions. A separate pairing scenario counts selected debit/credit pairs
   once. A proposed Workspace theory preserves investigator wording and sources;
   it is not an automatically established finding.
6. **Export:** the full capture retains the applied account/date scope, originals,
   source references and decisions. Table-view filters form a separate captured
   population. Original source-file inclusion is optional and verifies bytes.

## Repeating browser acceptance safely

These scripts only read their existing labelled fixtures; their case/report files
must already exist. They sign in through the browser and write local result files:

```sh
node scripts/check_local_reference_review.cjs
node scripts/check_local_undated_page_scan.cjs
node scripts/check_local_amount_range.cjs
node scripts/check_local_current_native.cjs
node scripts/check_local_duplicate_bulk.cjs
```

Do not run a collection of every `check_local_*` script. Some older checks create
cases or deliberately correct, finalise or adjudicate readings. In particular,
completed native-delta, chain-theory, account-party and PDF-finalisation writers
have guards; inspect their checkpoint files instead of deleting those guards.
The scripts above are checks of retained examples, not a replacement for testing
a fresh upload/review workflow. See the retained development checklist for that
acceptance and for features still under development.

## Stop and resume

Stop each of the four application terminals with Ctrl-C, then:

```sh
docker compose -f docker-compose.local.yml stop
```

Data remains in the local volumes. Resume with the same startup commands; do not
remove volumes, run a reset or recreate fixtures. If a port is already occupied,
check which existing local process owns it before starting a second copy.

## Scope still unvalidated

The launcher deliberately clears real model keys and prevents repository `.env`
loading. External AI extraction, chat, embeddings and transcription are not
validated by this check. The engine's `openai` health flag reports a nonempty
key, which is not provider connectivity; this checker deliberately excludes it
from the local-readiness claim. Dependency ranges and Docker image tags are not a
fully frozen release lock. Deployment is the repository's existing push-triggered
server process; these commands neither push nor deploy.
