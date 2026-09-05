# Loupe build state

Where the work stands. Rewritten whenever a unit lands. Durable rules live in
`CLAUDE.md` at the repo root, not here.

**Last updated:** 5 September 2026 (records the sandbox/baseline infrastructure
unit, `0cdd3f4` — no product code changed)

---

## Position

- **Branch:** `integration/evidence-main-reunion`
- **Head when this was written:** `0cdd3f4`
  (`0cdd3f4517105c505a965349f9c4df5efa72d4c7`), "Make the sandbox able to run the
  suites, and correct the baselines", parent `0ce3fdd`. **Confirm the real tip
  with `git log --oneline -5`** at the start of every session rather than
  trusting this line.
- **Nothing is pushed.** Push is blocked; Neil pushes.

### Uncommitted

Nothing tracked. The tree is clean.

Still untracked and still un-removable from a session (workspace denies
`unlink`), unchanged for three sessions now — Neil has to delete these from his
side:

- `backend/services/financial/export_manifest.py.bak`
- `backend/services/financial_export_service.py.bak`
- `frontend_v2/src/__probe.test.ts`

### Scale, measured from git this session

73 commits since `c4246c0` (27 August), counting `0cdd3f4`.
`backend/services/financial/`: **44 modules**, **32,452 lines** by `wc -l`.
`backend/tests/test_financial_*.py`: **47 files**, **3,057 tests** by the
discover run. All three unchanged from last session in file terms; the test
count rose from 3,053 because two files that previously contributed a single
import-failure placeholder each now contribute their real bodies.

---

## What this session did

Two things, in order. The first was not a build item and was not planned.

### 1. Answered a scoping question (no code)

Neil asked how much work is left on the financial piece. Reported, and re-checked
against source rather than memory:

- Item 12 has two remainders. The frontend read path is one unit. Wiring
  `ingest_native_reading` is the substantial one.
- **`ingest_native_reading` has no caller anywhere outside its own test file.**
  Re-verified this session by grep across `backend/` excluding `tests/`: the only
  hits are its own `def`, and its import and `__all__` entry in
  `services/financial/__init__.py`. So the Postgres ledger has a tested writer
  and a tested reader and **no production writer at all**. Any screen built
  against `GET /api/financial/ledger` today reads a table nothing fills.
- Both financial routers **are** wired into `routers/__init__.py` and `main.py`.
  Verified, not assumed.
- `tracing.py` and `exhibit.py` are exported from the package but have no caller
  in `routers/` or `services/`. Unchanged.
- Item 11 stays blocked on the correction-versus-re-ingestion ruling.
- Items 14–17 stay parked.

An estimate of roughly seven to eight sessions for everything currently
unblocked was given to Neil and labelled as an estimate.

### 2. The infrastructure unit (`0cdd3f4`)

Neil's instruction was "I want you to be able to work through this now. What
blockers do we need to solve?", then, on the findings, "commit as one infra
unit" and "clean, no expected failures".

Two files changed. **No product code, no test code, no behaviour.**

- `CLAUDE.md` — Environment, Tests and Git sections.
- `frontend_v2/vitest.config.ts` — one line:
  `cacheDir: process.env.VITE_CACHE_DIR || undefined`. Env-gated, so with the
  variable unset the config behaves exactly as before. Nothing outside this
  sandbox changes.

#### What was actually wrong

**The backend suite could not run at all.** The sandbox starts with *no* backend
dependencies — not `sqlalchemy`, not `fastapi`, not `pydantic`. The repo `venv/`
is a stale Python 3.14 with nothing installed and is not what the suite runs on.
`backend/requirements.txt` is the wrong instrument because it pulls
`openai-whisper` and therefore torch, for no benefit to this suite. Seventeen
pinned packages are sufficient and install in about twenty seconds. The exact
one-line command is now in `CLAUDE.md` under Tests; it is not repeated here,
because a command in two places drifts.

**The recorded backend baseline was wrong, and the way it was wrong was hiding
two dead test files.** `2933, FAILED (errors=1)` treated a `jose`
ModuleNotFoundError as permanent. It was never permanent, only a missing package.
Because it was accepted as expected, nobody noticed that `test_financial_router`
and `test_financial_ledger_router` were failing at *import* and never executing a
single test body. With the packages present:

- Suite: **Ran 3057 tests, OK (skipped=12). Zero errors, zero failures.**
- `test_financial_ledger_router.py` runs its **5 tests for the first time; all
  pass.** That is the router the frontend unit targets, so this matters directly
  to the next item.

The `services.agent` → `langchain_openai` gap raised as an open question last
session is **closed**: it was three more packages (`langchain-core`,
`langchain-openai`, then `langgraph` and `langgraph-checkpoint`), all now in the
bootstrap line.

**The vitest browser project was silently running zero tests.** The workspace
`unlink` denial was recorded as a cosmetic git warning. It is not only that: it
aborts the browser project during Vite dependency optimisation, before
collection, in about 150ms — and `passWithNoTests: true` then reports a clean
"no tests" result, so the failure looked like success. Pointing `cacheDir` at
`/tmp` fixes it. The browser project now runs **2 files, 4 tests**.

**Two git-procedure defects, both now fixed in `CLAUDE.md`.**

- `user.name` and `user.email` are unset in the sandbox and git's guess
  (`<session-user>@claude.(none)`) is unusable, so setting only `GIT_AUTHOR_*`
  leaves `commit-tree` failing with `fatal: unable to auto-detect email address`.
  The `GIT_COMMITTER_*` pair is now part of the documented command. This had been
  carried as an open question for at least two sessions.
- The fixed `/tmp/loupe.index` path does not survive a session change. `/tmp` is
  sticky and the sandbox user is different every session, so the file left by an
  earlier session (`nifty-ecstatic-gauss`, 1 September) is owned by another uid
  and can be neither removed nor written. The procedure failed on its very first
  line with `Operation not permitted`. The path is now derived:
  `/tmp/loupe-$(id -un).index`.

#### Verified baselines, all run this session

- Backend financial suite: **3057 tests, OK (skipped=12)**.
- `test_financial_ledger_router.py` alone: **5/5 pass**.
- Frontend unit project: **54 files, 285 tests, pass**.
- Frontend browser project: **2 files, 4 tests, pass**.
- `npx tsc -b`: 0. `npx eslint .`: 0.
- Commit verified by diffstat against HEAD before writing the ref: exactly the
  two intended files. Tree tracked-clean after the ref update.

The old `CLAUDE.md` frontend line ("50 files, 246 tests") was stale; it is now
54 and 285.

---

## Durable facts, kept so no one rediscovers them

Everything about the bootstrap, the baselines, the `VITE_CACHE_DIR` requirement,
the playwright install, the storybook limitation and the git procedure now lives
in **`CLAUDE.md`**, because it does not change week to week. It is deliberately
not duplicated here. What follows is only what is still in flux.

### New this session

- **`chromadb` is deliberately absent from the bootstrap.** `VectorDBService`
  degrades gracefully and prints a warning that vector search is disabled. That
  warning is expected output, not a failure.
- **No live Postgres is needed for the financial suite.**
  `test_financial_transaction_query` builds SQLite in a temp directory. Verified
  by reading the test, not assumed.
- **`npx playwright install chromium` works; `--with-deps` does not**, because it
  needs sudo and the sandbox sets the no-new-privileges flag. The browser binary
  is about 106 MiB and installs in roughly a minute.
- **The storybook vitest project cannot run here.** Its iframe orchestrator fails
  against `localhost` (`Received URL: unknown`) and it completes 3 of 36 files.
  A bare `npx vitest run` with no `--project` will attempt it and hang past ten
  minutes. **No story covers financial code**, so this does not block the
  financial build, but it means "vitest is green" only ever refers to the unit
  and browser projects. **Not investigated further and should not be without a
  ruling from Neil** — it is off the critical path.
- **`--reporter=basic` is not a valid vitest v4 reporter** and fails with
  "Failed to load custom Reporter from basic". Use the default reporter.

### Carried forward, still true

- **SQLAlchemy flush ordering does not follow raw ForeignKeys.** With no ORM
  `relationship()` between two mappers, commit the parent row first, then the
  dependent row in a second commit.
- **The full engine pytest suite cannot run on 3.10** — pre-existing
  `from datetime import UTC` in
  `evidence-engine/app/services/pipeline_run_state.py` is 3.11+ only.
- **The exports guard needs no edit for a new module**, as long as the module
  contributes names through `__init__.py` and has no module-level `__all__`.
- A bare module-name grep against `requirements.txt` installs the wrong package
  for `jose`: the line is `python-jose` and plain `jose` is an unrelated
  Python-2-era package that fails to import. Now moot, since the bootstrap line
  names packages explicitly, but recorded in case a resolver script is ever
  written.

---

## Build order

1–7. **Done.** Through the text-alignment tier and commit `3784dbe`.

8. **Done.** Financial subsystem description for Alex, delivered 1 September.

9. **Done.** Suspect-amount detection, `0910d9f`.

10. **Done.** Per-transaction source locator through the writers, `0d6b399`.

10a. **Done (1 September, no code).** Wiring investigation closed; triage out of
    the build.

11. Correction storage. **Still blocked on the correction-versus-re-ingestion
    question, below.**

12. Both halves of the "both stores" ruling are built — Neo4j by `de7ef21`,
    Postgres by `a9e0d29`. Two remainders:
    - **Frontend consumption of `GET /api/financial/ledger`.** Ruled by Neil as
      the next unit. **This is what the next session picks up.** Nothing on the
      frontend calls the endpoint yet. Note the sequencing risk recorded above:
      the ledger has no production writer, so this screen will read an empty
      table until the next item lands.
    - **Wiring `ingest_native_reading` into production.** The larger of the two.
      Order relative to the frontend unit was ruled this session: frontend
      first.

13. User-defined view tabs. Named snapshots of filter state, persisted,
    creatable, renameable, deletable. Also expose source document type onto the
    transaction row. (Two things, not one.)

### Parked (agreed with Neil, 1 September)

14. **Money movement over time.** No period-by-period series; every row carries
    `ordering_date`, so the data is there.

15. **Follow the money.** Chain across entities hop to hop. Distinct from
    doctrine tracing.

16. **Wire up tracing.** Built and tested, five doctrines, no caller, no route,
    no screen.

17. **Wire up exhibit tagging**, which needs an export path first.

---

## Open questions, waiting on Neil

**Correction versus re-ingestion.** Unchanged, still open, still blocking item
11. Proposal on the table (a correction triggers a genuine re-run of the balance
identity; only a re-run that closes moves the class), not accepted.

**Is content-hash de-duplication meant to be call-scoped only?** Raised last
session, still unruled. `document_content_hashes` disambiguates duplicate content
within one `record_transactions()` call but not across two separate calls to the
same document. Not a blocker for the frontend unit.

**Capability with no route to the user.** `exhibit.py` and `tracing.py` remain
unrouted. Item 12's route-to-user gap is purely frontend and is the next unit.

**Provenance of `exhibit.py`.** Unchanged: confirmed valuable, but it came from a
proposed build order, not a stated Owl requirement.

### Closed this session

- ~~Should CLAUDE.md's commit procedure gain the committer-identity line?~~ Yes.
  Done in `0cdd3f4`.
- ~~The `services.agent` → `langchain_openai` import gap: fix or leave
  undocumented?~~ Fixed. Four packages, now in the bootstrap.
- ~~Should the `jose` error stay an expected baseline failure?~~ No. Ruled
  "clean, no expected failures". The baseline is 3057, OK.

---

## Standing flags

- **P0 is unreachable on the current corpus.** No document carries its own
  control totals in a form that qualifies.
- **Half two has only ever run against synthetic ledgers.**
- **The item-1 geometry machinery IS reached in production** at the
  evidence-engine layer, verified end to end 1 September. Triage is out of the
  build by ruling; do not reopen without a new ruling.
- **No row in the corpus carries a running-balance column.** 30,570 rows across
  325 documents.
- **The alembic migration `20260902_evidence_table_geometry` has not been applied
  to any real database from a session** — the sandbox has no Postgres. First
  deployment needs an `alembic upgrade head` on Neil's side.
- **The Postgres ledger has no production writer.** See item 12.

---

## Defects raised and not yet ruled on

Small, real, none blocking:

- `evidence-engine/tests/test_pdf_table_geometry.py::test_the_summary_agrees_with_the_payload_it_summarises`
  fails against current code: it asserts the summary's exact key set without
  `by_table_source`, which `geometry_summary` has emitted since `3784dbe`. A
  stale test, pre-existing.
- Model class is named `AdjudicationEvent`, not `Adjudication` (`ef9e33d`).
- Bulk processing above 50 files cannot work: `MAX_BATCH_SIZE = 50` against list
  paging at 250.
- 11 Capital One pages carry a full-page white image XObject, most likely
  whole-page redaction.
- `merging_properties` missing from `_ACTIVE_JOB_STATUSES`, plus a silent
  fall-through in `_sync_db_record_from_job`.
- `safe_float` does `round(f, 2)` and defaults to `0`.
- The `7d8289b` commit message understates what the commit did.
- Append-only is not enforced at the database.
- The p3 early-return limitation.
- `_get_dataset_metadata` uses all-or-nothing legacy detection.
- `execute_cypher_batch` takes unparameterised strings.
- `get_financial_transactions` compares `n.date` as a string.
- `RECOMMENDED_CONSTRAINTS` and `RECOMMENDED_INDEXES` need out-of-band
  application.
- Two defects in the mutation harness.
- `scripts/categorize_transactions.py:443` hardcodes `national telegraph`.
- `ProcessConfirmDialog.tsx` contains dead code.
- `frontend_v2/node_modules/.__dom_probe_leftover` left behind.
- The engine docstring in `evidence-engine/app/pipeline/pdf_extraction.py` claims
  table text is byte-identical to the pre-geometry path; false whenever the
  recovery pass replaces a `table_rectangle_only` reading.
- Recovered text-alignment chunks collapse empty cells in the `" | "` join and
  sweep footer prose into the table chunk. Geometry unaffected; full diagnosis in
  the `72d1b1a` revision of this file.
