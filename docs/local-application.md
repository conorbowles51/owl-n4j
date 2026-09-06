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

Verified 6 September 2026: migrations from an empty PostgreSQL database to head,
all service connections and OCR, native PDF rendering, both venvs' `pip check`,
3,497 financial tests (12 skipped), and the real duplicate/lock-contention check.
This is a working integration environment, not exhaustive application acceptance
testing. The dependency ranges and image major tags are not a complete frozen
release lock.
