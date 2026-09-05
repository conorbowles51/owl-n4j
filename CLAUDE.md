# Loupe

Read this first, every session, before doing anything else. Then read
`docs/loupe-build-state.md` for where the work currently stands.

This file holds what does not change. Anything that moves week to week belongs in
the build-state file, not here. A file with stale lines in it stops being trusted,
and an untrusted file is worse than no file.

---

## What this is

Loupe is a forensic intelligence platform built for **Owl Consultancy Group**, a
private investigations firm in Washington DC. It ingests evidence of mixed kind and
condition (bank statements, phone extractions, documents, interview material) and
turns it into something an investigator can rely on and defend.

**Neil Byrne** is the founder and the only engineer. He is the person in every
session.

**Alex** is an investigator at Owl. She is not an attorney and not technical. She
receives financial material through **productions from the prosecution**; she does
not issue subpoenas and cannot ask for native formats. Rules for writing to her are
at the bottom of this file.

The financial subsystem is the centre of gravity: `backend/services/financial/`,
about 41 modules, with a test file per module in `backend/tests/`.

---

## Working agreement

These are standing instructions from Neil. They are not preferences.

- **Enterprise grade or don't ship it.** "Please please please this has to be
  thorough and correct."
- **No assumptions.** "I need you to be more exact and stop making assumptions."
  If a claim can be checked by reading the source, read the source. Never state a
  fact about the code from memory when the file is right there.
- **Chunked work.** One unit at a time, finished, tested, committed. Commit each
  completed unit as it lands rather than batching several together.
- **Never invent a user story.** Do not assert what Alex or anyone at Owl thinks,
  wants, asks, has experienced, or would otherwise have missed. If the value of a
  thing cannot be stated as a fact about the system or the domain, ask Neil. This
  rule exists because it was broken.
- **Do not start build work when told to stop.** When a non-build task is in
  progress, it halts everything else until Neil says it is done.
- **Check before defending.** When Neil challenges something as wrong, verify it
  against the source and report what is actually there, including when the answer
  is that he is right.
- **Orient Neil before asking him anything.** `docs/loupe-build-state.md` is
  written for the next session to resume from. It is not a briefing for Neil and
  he has not read it. So a continued session does not open in that register.
  Before the first question, and before any request for a ruling, say in plain
  language what the thing under discussion is, where it stands, and what is
  actually missing. No internal vocabulary until it has been defined in the same
  message: not item numbers, not module names, not words like "runs", "reaper",
  "precheck" or "proof class" used as if they were already shared. **A question
  Neil cannot answer without opening a file is a badly asked question.** This
  rule exists because it was broken repeatedly, in the same way, at the start of
  session after session.

### Design rules already settled

- Documents arriving together do not have to be related. "This is often how
  evidence will come in until the larger case is understood."
- Do not fall back to geometry-based table detection when nothing is found. "That's
  far too simplistic an assumption to make."
- Do not hard-refuse a suspect amount. Flag it, cite it back to its source, and let
  the analyst confirm or edit. This applies to all transactions and all fields.
- When a value is corrected, both the machine reading and the correction stay in
  the system and stay visible, but it must be obvious which is real, and **only the
  corrected value is used in money flows, sums, totals and searches.**
- Proof class is computed, never set by hand, including by us. A class a person can
  raise is an opinion.

---

## Environment

The repo is mounted per session and **the absolute path changes every session**.
Resolve it once at the start; do not hardcode a path from a previous session.

- **The bash working directory resets unpredictably.** Every command must `cd` with
  an absolute path in the same invocation. Do not rely on a `cd` from a previous
  command.
- `Edit` requires a full prior `Read` of the file in the same session.
- **Do not read exit codes through a pipe.** The code you get back is the pipe's.
- Python is **3.10.12** only. No newer syntax. Use system `python3`.
- **Ignore the repo `venv/`.** It is stale: Python 3.14 and no packages installed.
  It is not what the suite runs on and activating it will waste a session.
- **The sandbox starts with no backend dependencies at all** — not `sqlalchemy`,
  not `fastapi`, not `pydantic`. The backend suite cannot run until they are
  installed. See Tests for the one-line bootstrap. `pip` has network access.
- `pip` needs `--break-system-packages`. Keep the whole install on **one line**;
  a trailing space after a `\` continuation makes pip fail with
  `Invalid requirement: ''`.
- Avoid `!r` inside f-strings in `python3 -c` one-liners; quoting breaks.
- `-t` is a `unittest discover` flag only.
- The workspace denies `unlink`. This produces harmless `tmp_obj_*` warnings from
  git, but it is **not** always cosmetic: it also aborts the vitest browser
  project before collection. `/tmp` allows `rm`.
- **Every scratch path in `/tmp` must carry the current user in its name**, e.g.
  `/tmp/tsc-$(id -un).out`. `/tmp` is sticky and the sandbox user changes every
  session, so a fixed name left behind by an earlier session is owned by another
  uid: redirecting into it fails with `Permission denied` and `rm` fails with
  `Operation not permitted`. This applies to the git index (see Git) and to
  anything else, including a file used only to capture a command's output — where
  the failure looks exactly like the command itself having failed.
- Case material and evidence files are **never committed**.

---

## Tests

### Backend bootstrap, once per session, before anything else

Nothing backend runs until this is done. It takes about twenty seconds. The full
`backend/requirements.txt` is **not** needed and should not be used: it pulls
`openai-whisper` and therefore torch, for no benefit to this suite.

```
pip install --break-system-packages --quiet "SQLAlchemy==2.0.46" "pydantic==2.12.5" "fastapi==0.123.9" "psycopg[binary]==3.2.13" "python-dateutil==2.9.0.post0" "lxml==6.0.2" "openpyxl==3.1.5" "neo4j==5.28.2" "alembic==1.14.0" "email-validator==2.2.0" "python-multipart==0.0.20" "openai==2.9.0" "python-jose==3.5.0" "langchain-core==1.5.0" "langchain-openai==1.1.7" "langgraph==1.0.6" "langgraph-checkpoint==4.0.0"
```

Seventeen packages. `pypdf` and `numpy` arrive transitively. `chromadb` is
deliberately absent: `VectorDBService` degrades gracefully and prints a warning
about vector search being disabled, which is expected and not a failure.

The import chain that forces most of this is `routers/__init__.py`, which imports
every router, so `routers.graph` pulls `openai` and `routers.agent` pulls
`langgraph`. Any router-level test drags the whole chain in.

### Backend financial suite, from the repo root

```
cd backend && env PYTHONPYCACHEPREFIX=/tmp/pyc_st PYTHONDONTWRITEBYTECODE=1 \
  PYTHONHASHSEED=0 python3 -m unittest discover -s tests -p 'test_financial_*.py' -t .
```

Baseline after the bootstrap: **Ran 3057 tests, OK (skipped=12)**. There are **no
expected failures**. Any failure is yours.

The old baseline recorded here was `2933, FAILED (errors=1)` with a `jose`
ModuleNotFoundError treated as permanent. It was never permanent, only a missing
package, and it was masking the fact that `test_financial_router` and
`test_financial_ledger_router` were failing at import and never executing a single
test body.

No live Postgres is needed. `test_financial_transaction_query` builds SQLite in a
temp directory.

The package surface is guarded by `backend/tests/test_financial_exports.py`. A new
module exported from `services/financial/__init__.py` must be added there.

### Frontend, from `frontend_v2/`

Always set the Vite cache to `/tmp`, or the workspace `unlink` denial aborts the
browser project before it collects anything, and `passWithNoTests: true` then
reports a clean "no tests" so the failure is silent. **The cache path must carry
the current user**, like every other `/tmp` path here: `/tmp` is sticky and the
sandbox user changes every session, so a directory left by an earlier session is
owned by another uid and the browser project dies with `EACCES ... rmdir` —
reporting "no tests", which is the same silent failure.

```
VITE_CACHE_DIR=/tmp/vite-cache-$(id -un) npx vitest run --project unit
VITE_CACHE_DIR=/tmp/vite-cache-$(id -un) npx vitest run --project browser
npx tsc -b
npx eslint .
```

Baseline: unit **64 files, 437 tests**; browser **2 files, 4 tests**; `tsc -b`
returns 0; eslint returns 0. Use `fireEvent`, not `userEvent`. The unit project
takes about 75 seconds; that is not a hang.

**The browser project needs Chromium, and it is a per-session install.** The
browsers live under `/sessions/<session>/.cache/ms-playwright`, which is new
every session, so on a fresh session the gate fails with `Executable doesn't
exist ... headless_shell` and again reports "no tests". Install it once, before
the browser gate. Stage the download on `/sessions`, because `os.tmpdir()` is
`/tmp` on the root filesystem, which is 99% full:

```
mkdir -p /sessions/<session>/tmpdl && TMPDIR=/sessions/<session>/tmpdl \
  npx playwright install chromium
```

Do **not** pass `--with-deps`, which requires root and fails.

**Never read a "no tests" result as green.** All three failure modes above
produce it.

**The `storybook` project cannot run in this sandbox.** Its iframe orchestrator
fails against `localhost` and it completes 3 of 36 files. No story covers financial
code, so this does not block financial work, but "vitest is green" means the unit
and browser projects only. Do not spend a session trying to fix it without a
ruling from Neil.

`npx vitest run` with no `--project` will try storybook and hang for over ten
minutes. Always name the project.

---

## Git

**Branch is `integration/evidence-main-reunion`. Never merge to main.**

**Push is blocked. Neil pushes.** Never attempt it.

**Never modify git config.** The write procedure below sets both identities per
commit instead.

**`user.name` and `user.email` are unset in the sandbox**, and git's guess
(`beautiful-awesome-franklin@claude.(none)`) is not usable. Setting only the
`GIT_AUTHOR_*` pair is therefore not enough: `commit-tree` still fails with
`fatal: unable to auto-detect email address`. The `GIT_COMMITTER_*` pair must be
set on the same command.

**The index path must be unique per session.** `/tmp` is sticky and the sandbox
user changes every session, so a fixed `/tmp/loupe.index` left behind by an earlier
session is owned by a different uid: it cannot be removed or written, and the
procedure fails at the first line with `Operation not permitted`. Derive the name
from the current user instead.

Commits are written through a temporary index so the real index is never disturbed:

```
IDX=/tmp/loupe-$(id -un).index
rm -f "$IDX"
export GIT_INDEX_FILE="$IDX"
git read-tree HEAD
git add <explicit paths, never -A and never .>
git write-tree
git diff --stat HEAD <tree>          # verify before committing
GIT_AUTHOR_NAME="Neil Byrne" GIT_AUTHOR_EMAIL="thenofisamizdat@gmail.com" \
  GIT_COMMITTER_NAME="Neil Byrne" GIT_COMMITTER_EMAIL="thenofisamizdat@gmail.com" \
  git commit-tree <tree> -p HEAD -m "<message>"
```

Then `Read` the ref file, `Write` the new sha to
`.git/refs/heads/integration/evidence-main-reunion`, restore the index with
`cat "$IDX" > .git/index`, and verify `git status --porcelain | grep -v '^??'`
is empty. The `cat` redirect truncates rather than unlinks, so it is not affected
by the workspace `unlink` denial.

Commit messages describe what changed and why in plain language. They are load
bearing: they are the only durable record of reasoning that survives between
sessions.

---

## Writing to Alex

Every rule here was established by having a draft rejected. They cost real time to
learn.

- **No em dashes. Anywhere.**
- No internals. No module names, no file formats, no parsers, no arithmetic, no
  floating point.
- She is an investigator, not an attorney. No rule numbers, no case citations.
  Translate a legal consequence into what it means for the work.
- She receives productions. Advice about subpoenas or asking for native formats is
  useless to her.
- **Never assert what she thinks, wants, asks, has seen, or would have missed.**
- **Do** state value: what a capability makes possible or prevents, as a fact about
  the system and the domain.
- Explain what something means **to an investigation**, not what it means as data.
  Abstract framing gets rejected: "every total silently covers a subset" means
  nothing to a reader.
- Where a failure or an outcome is mentioned, say what it means and what the user
  can do about it.
- **Never describe a visualization.** Say what the user can learn and do.
- Never lead with or dwell on the decimal-point OCR example.
- Teammate tone, not a sales pitch. Pasteable into Teams as-is.
- Structure that works: two halves, making the ledger trustworthy, then what a
  trustworthy ledger lets you do. Anything not yet built goes in a clearly separate
  section at the end, because the moment one item is aspirational the reader has to
  wonder about the rest.
- Lead-ins are bold **and** italic: `***like this.***`

---

## Session hygiene

The context window is spent mostly on reading source, which is also what makes the
work correct. So sessions end for a good reason, not because they ran out.

- Scope a session to **one build item**.
- End at a boundary: a unit landed and committed. At that point git holds most of
  the state and the handoff is cheap.
- **Write the state file before ending, not after compaction.** After compaction the
  detail needed to write it accurately is already gone.
- Do not stop mid-item with a dirty tree. If it is unavoidable, the state file must
  say exactly what was in flight.
- Signs the session is already past its stopping point: re-reading a file read
  earlier in the same session, asking Neil something he already answered, or a
  compaction having just occurred.

### After every commit, without being asked

A commit is the clean boundary, so it is the trigger. As soon as a commit lands,
before starting anything else:

1. Rewrite `docs/loupe-build-state.md`. New head and commit subject, what is now
   uncommitted, where the build order stands, anything newly parked, any question
   raised that Neil has not ruled on, any defect found and not fixed.
2. Record anything a fresh session would otherwise have to rediscover: a command
   that failed and the form that worked, a fact established by reading source, a
   decision made and its reasoning.
3. Commit the state file.
4. Then tell Neil **in bold** that the state is written and this is a good point to
   start a new session, and say in one line what the next session should pick up.

Do this even when there is plenty of window left. The point is that the handoff is
always current, so a session can be ended at any moment without losing anything. Do
not carry on into the next item first and write the state afterwards, because by then
the detail that made the state accurate is the thing that has been spent.
