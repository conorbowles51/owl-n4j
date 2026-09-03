# Loupe build state

Where the work stands. Rewritten whenever a unit lands. Durable rules live in
`CLAUDE.md` at the repo root, not here.

**Last updated:** 3 September 2026 (records the Postgres ledger read API unit,
`a9e0d29` — the other half of item 12's "both stores" ruling)

---

## Position

- **Branch:** `integration/evidence-main-reunion`
- **Head when this was written:** `a9e0d29`
  (`a9e0d29fd32ac3c91aa8e5d1d2d7ffe69e42d7e9`), "Add a Postgres ledger read
  API", parent `7196415`. **Confirm the real tip with `git log --oneline -5`**
  at the start of every session rather than trusting this line.
- **Nothing is pushed.** Push is blocked; Neil pushes.

### Uncommitted

- Two stray `.bak` files that should be deleted, not committed:
  `backend/services/financial/export_manifest.py.bak`,
  `backend/services/financial_export_service.py.bak`. Untracked, harmless,
  still cannot be removed from a session (workspace denies `unlink`). Neil has
  to remove them from his side.
- `frontend_v2/src/__probe.test.ts` — same restriction, unchanged from last
  session. Still needs a session-external delete.

No tracked changes are outstanding. The tree is otherwise clean of build work.

### Scale, measured from git

71 commits since `c4246c0` (27 August), counting `a9e0d29`.
`backend/services/financial/`: **44 modules** (up from 43 — `transaction_query.py`
is new), **32,452 lines** by `wc -l` (up from 32,221).
`backend/tests/test_financial_*.py`: **47 files** (up from 45 —
`test_financial_transaction_query.py` and `test_financial_ledger_router.py`
are new), **3,053 tests** by the discover run (up from 3,041 — accounted for
exactly: +11 real tests in the new service-level file, +1 for the new
router-level file's import-failure placeholder; see Verification below for
why that file cannot import in this sandbox).
Frontend: unchanged this unit, not re-run — no frontend file touched.

---

## What this session did: the Postgres ledger read API (`a9e0d29`)

### The unit

The "both stores" ruling for item 12 has two halves: Neo4j (closed end to end
by `de7ef21`, last session) and Postgres. Nothing before this unit could read
the relational ledger tables `record_transactions` writes into — the tables
existed, the writer existed, and there was no way back out. This unit is that
read path. One commit, seven files, 861 insertions, 0 deletions.

- `backend/services/financial/transaction_query.py` (new). `list_transactions`
  queries one case's rows, defaulting to `LedgerStatus.admitted` — the
  population every other total in the ledger is filtered to — with optional
  `account_id`, `ledger_status`, and an `ordering_date` range via
  `start_date`/`end_date`. `ordering_date` is the column the ledger itself
  orders and reconciles by, not any of the four printed dates a row may also
  carry, so that is deliberately what the range bounds. `to_view` shapes a row
  into a plain JSON-serialisable `TransactionView`: dates as ISO strings,
  closed-vocabulary columns (`ledger_status`, `quarantine_reason`, ...) as
  plain primitives, and the locator lifted out of `provenance` rather than
  left buried in it.
- `backend/routers/financial_ledger.py` (new). `GET /api/financial/ledger`,
  read-only — admitting, correcting, or quarantining a row stays with the
  ingestion and adjudication services that act with a run and an actor behind
  them. Same `prefix="/api/financial"`, same `get_current_db_user` +
  `case_access_dependency` gating as the existing `routers/financial.py`,
  confirmed by direct comparison of the two files. A `LedgerQueryError` (for
  example `start_date` after `end_date`) becomes a 400; an unknown
  `ledger_status` string is also a 400, not a 500; anything else unexpected is
  a 500 with the case id logged.
- `backend/routers/__init__.py`, `backend/main.py` — wired in, same pattern as
  every other router.
- `backend/services/financial/__init__.py` — exports `LedgerQueryError`,
  `TransactionView`, `list_transactions`, `to_view`. `test_financial_exports.py`
  needed no edit: its guard is a generic AST walk over every module in the
  package, so a module is covered the moment it contributes a name to
  `__all__`. Confirmed by running that file alone (5/5 pass) rather than
  assuming it from the docstring.

**Tests.** `test_financial_transaction_query.py`, 11 tests against a real
sqlite-backed session (`ListTransactionsTests`: default-to-admitted, explicit
status override, case isolation, account filter, date-range filter and its
refusal when `start_date` is after `end_date`, ordering by `ordering_date`
then `row_index`; `ToViewTests`: ISO dates, closed-vocabulary primitives,
locator lifted out of provenance, whole-dict JSON shape).
`test_financial_ledger_router.py`, 5 tests, mirroring the house pattern in
`test_financial_router.py`: the handler is awaited directly with
`list_transactions`/`to_view` patched out, so these are about the router's own
job — status-string parsing, error translation, response shape — not the
query logic underneath.

### Real bugs found and fixed, in my own new test file, before this counted as passing

None of these are product bugs; all four were test-authoring mistakes,
caught by the writer's own constraints doing exactly what they are for:

1. `test_orders_by_ordering_date_then_row_index` passed three drafts in one
   `record_transactions()` call with `row_index` values `(0, 1, 0)`. The
   writer refuses two drafts in the same batch claiming the same
   `row_index` (`TransactionFieldError`). Fixed by using `(2, 1, 0)`.
2. Three tests (`test_defaults_to_admitted_rows_only`,
   `test_an_explicit_status_overrides_the_default`, `test_filters_by_account`)
   called `record_transactions()` twice against the same source document with
   identical default reading content. `content_hash` occurrence-counting
   (`document_content_hashes` in `references.py`) disambiguates duplicate
   content *within one call's list*, not across two separate calls — its
   `seen` counter is local to the call. Two calls with identical content on
   one document therefore produce the same hash and collide on the
   `(source_document_id, content_hash)` unique constraint. Fixed by giving the
   second draft in each test distinct content (`reading(amount_minor=13_50)`).
   **Worth a design question for Neil**, not acted on here: is
   call-scoped-only de-duplication the intended contract, or should it be
   documented explicitly on `document_content_hashes` so the next person
   doesn't rediscover this by hitting the same constraint?
3. Setting `row.ledger_status = LedgerStatus.quarantined.value` directly
   without also setting `row.quarantine_reason` violates
   `ck_financial_transactions_quarantine_coherent`
   (`quarantine_reason IS NOT NULL) = (ledger_status = 'quarantined')`).
   Fixed by also setting `quarantine_reason = "unreadable_row"`, a valid value
   from the closed vocabulary in `postgres/models/financial.py`
   (`_QUARANTINE_REASONS`).

### Verification

- `test_financial_transaction_query.py` run alone: **11/11 pass.**
- `test_financial_exports.py` run alone: **5/5 pass**, confirming
  `transaction_query` is reachable from the package surface with no edit to
  the guard test.
- Full backend financial suite,
  `python3 -m unittest discover -s tests -p 'test_financial_*.py' -t .`:
  **Ran 3,053 tests, FAILED (errors=2, skipped=12).** Both errors are the
  documented baseline `jose` gap (see Durable facts), now appearing twice
  because this unit adds a second test file that imports the `routers`
  package. Zero unexpected failures, zero unexpected errors.
- **`test_financial_ledger_router.py`'s own test bodies could not be executed
  in this sandbox** — see the new durable fact below on the `services.agent`
  → `langchain_*` chain. What was verified instead, all by direct inspection
  rather than assumption: `list_transactions`'s actual signature
  (`services/financial/transaction_query.py`) matches, argument-for-argument,
  both what `financial_ledger.py` calls it with and what the test file's
  mocks assert were called; and the new test file fails at the **identical
  import line, for the identical reason**, as the pre-existing
  `test_financial_router.py` — proof this is a pre-existing environment gap
  in a subsystem this unit never touched (`routers/agent.py`), not a
  regression from this unit.
- Diffstat verified against HEAD before committing: exactly the 7 intended
  files, 861 insertions, 0 deletions, nothing else. Tree tracked-clean after
  the ref update.

---

## Durable facts from this and earlier sessions, kept so no one rediscovers them

### New this session

- **This sandbox's system Python starts with zero backend dependencies.**
  Unlike a previous session's experience (see "sandbox was recycled
  mid-work" below), this one never had them to lose — `/usr/bin/python3`
  (3.10.12) was bare from the start of the session. Installed the pinned
  versions from `backend/requirements.txt` one at a time via
  `pip3 install --break-system-packages -q <pkg>==<pin>`, to the user's
  site-packages. **This is sandbox-environment setup, not a project
  dependency change** — `requirements.txt` was not edited, and nothing about
  this is part of the commit.
- **The repo's `backend/venv` is unusable for a second, independent reason
  beyond the broken interpreter symlink already on record.** Its
  `lib/python3.14/site-packages` (not even the 3.13 the broken symlink
  implies — internally inconsistent) contains macOS (`darwin`)-compiled
  binaries, so it could not run in this Linux sandbox even with a working
  interpreter path. It is also missing `sqlalchemy` entirely despite the pin
  in `requirements.txt`. Confirmed by direct inspection, not assumed from the
  symlink alone. Do not attempt to repair it; install to system Python
  instead.
- **A bare module-name grep against `requirements.txt` can install the wrong
  package.** A loop that greps for the bare import name `jose` will not find
  the line `python-jose==3.5.0` and falls through to `pip install jose` —
  which is a real, different, unrelated PyPI package (`jose` 1.0.0, a
  Python-2-only relic; importing it raises `SyntaxError: Missing
  parentheses in call to 'print'`). If a resolver script is ever written for
  this, it needs to check both the bare name and common prefixed forms
  (`python-<name>`) before falling back to latest.
- **`jose` alone is not the full router-import gap in this sandbox; there is
  a second, deeper one.** With `python-jose==3.5.0` and `email-validator==2.2.0`
  installed (purely to attempt full execution of the new router-level test
  file's bodies, not as a baseline change), the `routers` package import
  chain gets past `services/auth_service.py` and `services/users.py` and
  fails further down: `routers/agent.py` → `services/agent/__init__.py` →
  `services/agent/service.py` → `services/agent/graph.py` →
  `from langchain_openai import ChatOpenAI` (after first needing
  `langchain-core==1.5.0`, then `langchain_openai`, neither pinned exactly
  for two of the four `langchain-*` lines in `requirements.txt` —
  `langchain-anthropic` and `langchain-google-genai` are range-pinned, not
  exact). This chain is entirely inside `services/agent`, a subsystem this
  unit never touched, and it affects **every** router-level financial test,
  old and new, identically — confirmed by running
  `test_financial_router.py` (pre-existing) and getting the exact same
  traceback. Did not chase this further: unbounded, off-task, and
  `python-jose` was left installed this session but the underlying baseline
  gap (documented as `jose` in CLAUDE.md) is superseded by this deeper one
  the moment `jose` itself is resolved. **Flagged for Neil below** rather
  than resolved.
- **A `/tmp/loupe*.index` filename can be stuck owned by a different
  sandbox-session user and refuse to `rm` even with a fresh session's own
  account** (`Operation not permitted`, cross-UID, not the workspace's own
  unlink restriction). Pick a fresh, never-before-used index filename per
  commit rather than assuming the documented `/tmp/loupe.index` is free;
  this session used `/tmp/loupe-elt.index`.

### Carried forward

- **The commit procedure in CLAUDE.md is still missing committer identity.**
  `git commit-tree` fails with "Committer identity unknown" on a fresh
  sandbox. Fix used again successfully: also set
  `GIT_COMMITTER_NAME="Neil Byrne" GIT_COMMITTER_EMAIL="thenofisamizdat@gmail.com"`
  on the same command as `GIT_AUTHOR_*`. Still unresolved in CLAUDE.md itself;
  flagged again below.
- **SQLAlchemy flush ordering does not follow raw ForeignKeys.** With no ORM
  `relationship()` between two mappers, commit the parent row first, then the
  dependent row in a second commit.
- **The full engine pytest suite cannot run on the 3.10 sandbox, and never
  could** — pre-existing `from datetime import UTC` in
  `evidence-engine/app/services/pipeline_run_state.py` is 3.11+ only. Not
  touched this session; recorded so it isn't rediscovered.
- **`routers.evidence` cannot be imported in this environment** via the same
  family of import chains documented above; tested statically instead
  (`tests/test_financial_route_check.py` pattern: AST over router source).
- **The exports guard needs no edit for a new module**, as long as the module
  contributes names through `__init__.py` and has no module-level `__all__`.
  Confirmed again this session for `transaction_query`.
- Frontend verification trio, unchanged, not run this session (no frontend
  file touched): `npx vitest run`, `npx tsc -b`, `npx eslint .` from
  `frontend_v2/`.

---

## Build order

1–7. **Done.** Through the text-alignment tier and commit `3784dbe`.

8. **Done.** Financial subsystem description for Alex, delivered 1 September.

9. **Done.** Suspect-amount detection, `0910d9f`.

10. **Done.** Per-transaction source locator through the writers, `0d6b399`.

10a. **Done (1 September, no code).** Wiring investigation closed; triage out
    of the build.

11. Correction storage. **Still blocked on the correction-versus-re-ingestion
    question, below.**

12. **Both halves of the "both stores" ruling are now built.** Neo4j side
    closed end to end by `de7ef21`. Postgres side — the ledger read API —
    closed by `a9e0d29` this session. What remains, unruled on order:
    - **Nothing on the frontend calls the new `GET /api/financial/ledger`
      endpoint yet.** The backend half exists; there is no screen reading it.
    - **Wiring `ingest_native_reading` into production** — the ledger still
      has no production writer. Whether this comes before or after the
      frontend consumption of the read API is unruled.

13. User-defined view tabs. Named snapshots of filter state, persisted,
    creatable, renameable, deletable. Also expose source document type onto
    the transaction row.

### Parked (agreed with Neil, 1 September)

14. **Money movement over time.** No period-by-period series; every row
    carries `ordering_date`, so the data is there.

15. **Follow the money.** Chain across entities hop to hop. Distinct from
    doctrine tracing.

16. **Wire up tracing.** Built and tested, five doctrines, no caller, no
    route, no screen.

17. **Wire up exhibit tagging**, which needs an export path first.

---

## Open questions, waiting on Neil

**Correction versus re-ingestion.** Unchanged, still open, still blocking
item 11. Proposal on the table (a correction triggers a genuine re-run of the
balance identity; only a re-run that closes moves the class), not accepted.

**Capability with no route to the user — narrowed again.** `exhibit.py` and
`tracing.py` remain unrouted. Item 12's route-to-user gap is now purely
frontend: the Postgres ledger read API exists and is tested, but nothing on
the frontend calls it.

**Should CLAUDE.md's commit procedure gain the committer-identity line?**
Unchanged from last session — still fails on a fresh sandbox without it.

**Is content-hash de-duplication meant to be call-scoped only?** New this
session (see bug 2 above). `document_content_hashes` disambiguates duplicate
content within one `record_transactions()` call but not across two separate
calls to the same document. This is currently just a fact discovered while
writing tests, not a ruling — worth a decision on whether it needs
documenting on the function itself, or whether cross-call duplicate content
on one document is expected to be refused some other way.

**The `services.agent` → `langchain_openai` import gap — worth fixing in this
sandbox, or leave undocumented like `jose`?** New this session. It blocks
executing the actual bodies of *every* router-level financial test in this
environment, old and new alike, the same way `jose` alone used to. Unlike
`jose`, it is not yet named anywhere in CLAUDE.md's baseline. If Neil wants
router-level test bodies runnable here, this needs either a documented
baseline addition (parallel to the `jose` line) or a scoped decision on how
far to install the `langchain-*` family.

**Provenance of `exhibit.py`.** Unchanged: confirmed valuable, but it came
from a proposed build order, not a stated Owl requirement.

---

## Standing flags

- **P0 is unreachable on the current corpus.** No document carries its own
  control totals in a form that qualifies.
- **Half two has only ever run against synthetic ledgers.**
- **The item-1 geometry machinery IS reached in production** at the
  evidence-engine layer, verified end to end 1 September. Triage is out of
  the build by ruling; do not reopen without a new ruling.
- **No row in the corpus carries a running-balance column.** 30,570 rows
  across 325 documents.
- **The alembic migration `20260902_evidence_table_geometry` has not been
  applied to any real database from a session** — the sandbox has no
  Postgres. First deployment needs an `alembic upgrade head` on Neil's side.

---

## Defects raised and not yet ruled on

Small, real, none blocking:

- **(1 Sept, this unit's verification, new):**
  `evidence-engine/tests/test_pdf_table_geometry.py::test_the_summary_agrees_with_the_payload_it_summarises`
  fails against current code: it asserts the summary's exact key set without
  `by_table_source`, which `geometry_summary` has emitted since `3784dbe`. A
  stale test, pre-existing, not from this unit.
- Model class is named `AdjudicationEvent`, not `Adjudication` (`ef9e33d`).
- Bulk processing above 50 files cannot work: `MAX_BATCH_SIZE = 50` against
  list paging at 250.
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
- **(1 Sept, wiring verification):** the engine docstring in
  `evidence-engine/app/pipeline/pdf_extraction.py` claims table text is
  byte-identical to the pre-geometry path; false whenever the recovery pass
  replaces a `table_rectangle_only` reading. Doc fix on the engine side.
- **(1 Sept, wiring verification):** recovered text-alignment chunks collapse
  empty cells in the `" | "` join and sweep footer prose into the table
  chunk. Geometry unaffected; full diagnosis in the `72d1b1a` revision of
  this file.
