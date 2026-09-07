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
assessment through the local backend. Candidate creation/review UI is not exposed
yet. The migration refuses downgrade while saved originals exist.
