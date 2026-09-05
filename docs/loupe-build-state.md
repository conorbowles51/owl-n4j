# Loupe build state

Where the work stands. Rewritten whenever a unit lands. Durable rules live in
`CLAUDE.md` at the repo root, not here.

**Last updated:** 5 September 2026 (records the ingest endpoint, `43f8358`)

---

## Position

- **Branch:** `integration/evidence-main-reunion`
- **Head when this was written:** `43f8358`
  (`43f835811071d627afd618827e8791cd787bbce9`), "Ingest endpoint: POST
  /api/financial/ingest, and the reading it shares with precheck", parent
  `3aa785e`. **Confirm the real tip with `git log --oneline -5`** at the start of
  every session rather than trusting this line.
- **Nothing is pushed.** Push is blocked; Neil pushes.
- **The build order lives in `docs/loupe-wiring-plan.md`,** not in this file. Read
  it before picking up work. It is an agreed plan and is not to be resequenced
  without a ruling from Neil.

### Uncommitted

Nothing tracked. The tree is clean.

Still untracked and still un-removable from a session (workspace denies
`unlink`) — Neil has to delete these from his side:

- `backend/services/financial/export_manifest.py.bak`
- `backend/services/financial_export_service.py.bak`
- `frontend_v2/src/__probe.test.ts` — a diagnostic left by the vitest
  investigation five sessions ago. It is **counted in the frontend baseline
  below** (it contributes 1 file and 1 test), so when it is deleted the unit
  numbers drop by one each and that is expected, not a regression.

Also untracked, and **not** mine — Neil's own documents, left alone:
`docs/IP_Protection_Strategy.docx`, `docs/ip-protection-strategy.md`,
`docs/owl-project-brief.md`.

### Scale

83 commits since `c4246c0` (27 August), counting `43f8358`.

Measured this session, after the commit:
`backend/services/financial/` **46 modules**, **33,759 lines**;
`backend/tests/test_financial_*.py` **50 files**, **3,164 tests**.

### Gate baselines as of `43f8358`

- **Backend financial suite: `Ran 3164 tests, OK (skipped=12)`.** Up from 3,103.
  The 61 new tests are the one new file (44) plus the growth of the router file
  (12 → 29). Skipped is unchanged at 12. **There are no expected failures.**
- **Frontend unit: 58 files, 354 tests, all passing.** The `CLAUDE.md` figure of
  54/285 is stale; 354 includes the stray probe test.
- **Frontend browser: 2 files, 4 tests.** `tsc -b` returns 0. `eslint .` returns 0.
  No frontend file was touched this session; the gate was run for completeness.

---

## What this session did

**Phase 1 item 2 of the wiring plan: the ingest endpoint.** Committed as
`43f8358`, six files, 2,061 insertions, 104 deletions.

`POST /api/financial/ingest` takes a native bank file already in evidence, reads
it through the same functions `/precheck` uses, opens an ingestion run, and
writes the document, its accounts, its periods and its rows. The run is
terminated on both paths. **This is the first production writer the Postgres
ledger has ever had.**

### What landed

- **`backend/services/financial/native_ingest_file.py`** (408 lines, new). The
  service. `IngestOutcome` (12 members), `READING_OUTCOMES`, `FileIngestion`,
  and `ingest_case_file`.
- **`backend/services/financial/native_precheck.py`** (675 → 837 lines). The
  parse-failure classifier factored out so both paths share it, rather than each
  deciding separately what an unreadable file is.
- **`backend/routers/financial_ingest.py`** (129 → 245 lines). The new route, and
  the permission split by path.
- **`backend/services/financial/__init__.py`** — exports.
- **`backend/tests/test_financial_native_ingest_file.py`** (946 lines, 44 tests,
  DB-backed) and **`backend/tests/test_financial_ingest_router.py`** (12 → 29).

### The outcome vocabulary

`IngestOutcome` has twelve members. Six are `PrecheckOutcome`'s own words spelled
identically, held to it by `READING_OUTCOMES` and a totality test, so a file
precheck called `unrecognised` cannot come back from ingest under another name.
`readable` is deliberately absent: once the file has been written the word is
`stored`.

The six ingest-only members are `stored`, `already_ingested`, `undescribable`,
`contradictory_period`, `refused` and `write_failed`. Note the split of
precheck's single `unattributable`: precheck cannot tell a document whose
accounts will not describe from one whose rows will not attribute without running
the writers, and the two call for different things — a document that cannot be
described is a file to look at again, a row naming an account the document never
introduced is a file that is missing part of itself.

**Only two outcomes become error statuses.** `not_found` is a 404 worded
identically to a file that does not exist, so asking cannot be used to learn what
another case contains. `write_failed` is a 500. Everything else returns **200**
carrying the outcome, because it is a fact about the evidence that belongs on the
screen beside the files that went in, not in the browser's error path.

### Decisions taken, and the evidence for each

**`ingestion_run` rather than the plan-named `open_ingestion_run`.** The wiring
plan names `open_ingestion_run` (`runs.py:288`), but `runs.py`'s own docstring
says "Prefer :func:`ingestion_run`, which cannot leave a run unterminated." The
context manager was used on that instruction. **Not a resequencing; flagging it
because the plan text says otherwise.**

**Permission is split by path, not by method.** `_READ_ONLY_PATHS` is an
allow-list holding `/api/financial/precheck`; everything else resolves to
`("evidence", "upload")`. Written as an allow-list rather than naming the write
paths so that a route added later without touching the resolver is gated at the
**higher** bar. The other way round it would silently inherit `case:view`, and a
mistake that hands a writer the reader's permission is not one the tests would
notice. Precheck is a POST and still resolves to `case:view`, because it takes a
file and does work rather than because it changes anything — the method cannot be
what decides the permission here.

**`reingest` was removed entirely, from both the service and the route.** This
reversed the design carried into the session and is the finding most worth Neil's
attention. See below.

**`already_ingested` returns 200, not 409.** It is a description of the case's
state, and the dialog needs to show it beside files that went in.

### The re-ingestion finding

The guard was justified by something false. The docstring claimed a second
ingestion "writes a second complete set of transactions and the case's money
doubles, silently". It cannot. Read from source, not assumed:

- `transactions.py:666` sets `ref_id = build_ref_id(document.sha256_at_ingestion,
  content)`.
- `references.py:394` makes that a pure deterministic function of the file digest
  and the row content, and says so: it takes the digest and not the document's
  surrogate id "so that re-ingesting the same file reproduces the same references
  rather than a fresh set".
- `postgres/models/financial.py:714` declares `uq_financial_transactions_case_ref`
  on `(case_id, ref_id)`.

So the same bytes read the same way produce byte-identical `ref_id`s and the
database refuses the second set outright. **Confirmed empirically** — removing the
guard produces an `IntegrityError`, not a doubled ledger.

What the early check is actually for is legibility. Without it, a second click
opens a run, writes a source document, its accounts and its periods, hits the
constraint on the first transaction, and returns a constraint name — everything
discarded, a failed run on the record, and nothing saying the plain thing, which
is that this file is already in the ledger.

`reingest` was therefore removed rather than kept. It cannot succeed for
unchanged bytes read the same way. The one case where it **would** succeed is a
re-read whose rows hash differently — a corrected window, a different assumed
currency, a genuinely different parse — and storing that leaves one case holding
two contradictory readings of one file with nothing able to say which governs.
That is `duplicates.py`, which is Phase 2 item 9 and not reachable from anywhere
today. An override belongs with it and not before it.

`test_the_schema_and_not_the_guard_is_what_stops_the_doubling` patches
`existing_document_for` to return `None` and asserts the constraint fires, so if
a future change ever made `ref_id` vary between readings the early refusal would
silently become load-bearing and that test would say so.

**This is a within-unit design call, not a reordering, so it did not need a prior
ruling — but Neil can overturn it.**

### The rollback fix, and the 25 seconds it was costing

Two tests left a run at `'running'` when it should have been `'failed'`. The
cause, found by reading rather than by guessing: the exception escaped the
`with ingestion_run(...)` block while the caller's session still held an open
write transaction. `ingestion_run` terminates the run on a **session of its own**,
by design, so the record survives the discarding of what it attempted — but the
two sessions then contend, and `runs._terminate_quietly` swallows the failure
deliberately rather than mask the real exception. The run was left for the reaper.

Fixed by rolling back inside the block before re-raising. Postgres happens not to
contend here; SQLite locks the whole file and does, which is how it surfaced.

**The new suite's runtime fell from 26.8s to 1.1s.** Those 25 seconds were SQLite
lock timeouts, which is the strongest confirmation the diagnosis was right.

### Verification

Both gates green and recorded above. The backend delta of 61 is exactly 44 plus
17, which confirms nothing else moved.

---

## Durable facts, kept so no one rediscovers them

The bootstrap, the baselines, the playwright install, the storybook limitation and
the git procedure all live in **`CLAUDE.md`**. Deliberately not duplicated here.

### `CLAUDE.md` is stale in one place — fix it when convenient

**`VITE_CACHE_DIR=/tmp/vite-cache` no longer works.** `CLAUDE.md` hardcodes that
path, but `/tmp` is sticky and the sandbox user changes every session, so a cache
directory left by an earlier session is owned by another uid and the browser
project dies with `EACCES: permission denied, rmdir '/tmp/vite-cache/vitest/...'`.
Use **`VITE_CACHE_DIR=/tmp/vite-cache-$(id -un)`**. This is the same per-user rule
`CLAUDE.md` states elsewhere, applied to a path `CLAUDE.md` itself exempts.

### New this session

- **The ledger cannot silently double, and it is the schema that guarantees it.**
  `ref_id` is deterministic from `(file sha256, row content)` and
  `uq_financial_transactions_case_ref` is on `(case_id, ref_id)`. Any future
  reasoning about duplicate ingestion starts here. **Do not restate the old claim
  that a second run doubles the money; it is wrong.**
- **A failure inside a `with ingestion_run(...)` block must roll back the
  caller's session before it leaves.** Otherwise the open write transaction
  contends with the run's own bookkeeping session, `_terminate_quietly` swallows
  it by design, and the run is left `running`. Costs nothing; removes the whole
  question.
- **`IntegrityError` text is not portable.** SQLite names the offending
  **columns**, Postgres names the **constraint**. Asserting either makes the test
  a test of which database the suite happens to run on. Assert the table name.
- **`financial_source_documents` is unique on
  `(ingestion_run_id, evidence_file_id)`** — one row per file per run. A test that
  hand-writes a second document for the same file needs a second
  `FinancialIngestionRun`, not just a new document id.
- **`evidence_files.stored_path` is `NOT NULL`.** The pathless file that
  production can actually hold is the **empty string**, not `None`. A test helper
  defaulting the parameter to `None` or `""` cannot express both "let the helper
  choose" and "give me the empty one" — use a module-level sentinel object.
- **DB-backed financial tests need file-on-disk SQLite, not `:memory:`,** because
  the run service opens sessions of its own and an in-memory database is not
  shared between them.
- **Prefer `ingestion_run` (the context manager) over `open_ingestion_run`.**
  `runs.py` says so itself: it cannot leave a run unterminated.
- **A compound `cmd; echo "exit: $?"` inside a longer `&&` chain can report an
  empty exit code.** Redirect to a per-user file and check separately. This is how
  `tsc -b` and `eslint` both appeared to have been verified when neither had.
- **The exports guard is automatic.** `tests/test_financial_exports.py` globs
  `*.py` in the package and asserts each module contributes at least one name to
  `__all__`. A new module needs **no manual list entry**, contrary to the note in
  `CLAUDE.md`. Re-confirmed this session against `native_ingest_file.py`.

### Carried forward, still true

- **A bare account number does not identify an account.** `AccountDraft.observed`
  (`accounts.py:400`) requires an IBAN, a routing number, or an identifier **plus
  an institution name**; otherwise `_account_draft` (`native_subjects.py:202`)
  falls back to `AccountDraft.unidentified` with
  `distinguisher = f"{sha256}:{ordinal}"`. So a BAI2 or MT940 statement that
  prints an account number and names no bank lands **unidentified with the number
  still visible**. What it costs is joining across documents. **Do not describe
  the flag as "no account number found" anywhere in the interface.**
- **The `distinguisher` is the file's own sha256,** stable across re-reads, and
  ingestion computes it the same way — so a precheck account key equals the key
  that gets written.
- **NACHA yields accounts and no periods.** It is not a statement. Verified across
  all four formats: camt 3/3 rows and a period, BAI2 3/3 and a period, MT940 2/2
  and a period, NACHA 1/1 and **no** period. Junk bytes give `unrecognised`.
- **The century window is required and never defaulted.** Three of the four native
  formats print two-digit years and none carries the century; `Case` carries no
  date range to derive one from. Max span
  `CENTURY_WINDOW_MAX_SPAN_YEARS = 99`; wider, or backwards, is a 400. **Both
  endpoints require `window_start` and `window_end`, so the dialog in Phase 1
  item 3 must collect the engagement period.**
- **A precheck verdict is not a promise the write will succeed.**
  `contradictory_period` and `already_ingested` are decided against rows already
  stored, not against the file. `would_ingest` is shorthand for one value of
  `outcome`, nothing more.
- **Reuse the shared fixture builders in `tests/test_financial_native.py`:**
  `WINDOW`, `camt_bytes(**kwargs)`, `bai2_bytes(**overrides)`,
  `mt940_bytes(**overrides)`, `nacha_bytes(records)`, `NACHA_SIMPLE`.
  `nacha_bytes` takes a **required positional**, unlike the other three.
- **Router tests await the handler directly and patch the service.** No test
  client. `test_financial_ledger_router.py` is the exemplar, including the
  module-level `patch.object(financial_ingest, ...)` form, which works only
  because the router imports the service function by name.
- **Turn a stray traceback in test output into an assertion.** Wrapping the case
  in `assertLogs(..., level="ERROR")` removes the noise **and** pins a real
  property. The router tests deliberately do *not* assert their one-line 500 log,
  matching `test_financial_ledger_router.py`.
- **Every Bash command needs its own absolute `cd`.** Broken twice three sessions
  ago: once it worked by luck, the second time it ran `grep` in the wrong
  directory and **hung for the full two minute timeout**, which does not look like
  a missing `cd` at all. Where a `cd` is awkward, `PYTHONPATH=<abs>/backend` works
  for one-liners.
- **Any scratch file in `/tmp` needs a per-user name,** including the git index.
- **`GIT_INDEX_FILE` does not survive between Bash invocations.** Staging and
  `git write-tree` must happen in one command. `commit-tree` can be a second
  command **provided it re-exports `GIT_INDEX_FILE` and passes the tree hash you
  already verified** — done again this session, worked again.
- **`&&`-chaining a `grep` that finds nothing silently kills the rest of the
  line.** Use `;` between verification steps.
- **`backend/venv/` poisons every repo-wide grep.** Always pass
  `--exclude-dir=venv --exclude-dir=__pycache__`, and `--exclude-dir=tests` when
  the question is whether something is wired in production.
- **Counting bare name occurrences does not tell you whether a component is
  mounted.** Grep for `import .*\bName\b` and list the files.
- **The house component-test conventions** are `render`/`screen` from
  `@testing-library/react`, `data-testid` for anything a test needs to find, and
  `fireEvent` never `userEvent`. Cleanest exemplar:
  `src/features/financial/components/TransactionSourceHighlight.test.tsx`.
- **`Badge` spreads `React.ComponentProps<"span">`.** Variants are `default`,
  `secondary`, `destructive`, `outline`, `success`, `danger`, `warning`, `info`,
  `amber`, `slate`. An unmapped lookup falls through to `default`, a **loud filled
  primary**, so a variant map must be explicit for every member.
- **`tsconfig` has `strict: true` but not `noUncheckedIndexedAccess`.**
- **React Query is `^5.90.21`**, so `isPending`, not `isLoading`.
- **Verify a `lucide-react` export before importing it.**
- **Any new code touching `amount_minor` must use `formatLedgerAmount`.** Other
  financial components use `toLocaleString("en-US", ...)` on a float, but those
  are Neo4j-backed `Transaction` rows, which carry floats, so they are not wrong
  today.
- **SQLAlchemy flush ordering does not follow raw ForeignKeys.** With no ORM
  `relationship()`, commit the parent row first, then the dependent row.
- **The full engine pytest suite cannot run on 3.10** — pre-existing
  `from datetime import UTC` in
  `evidence-engine/app/services/pipeline_run_state.py` is 3.11+ only.
- **The storybook vitest project cannot run here** and no story covers financial
  code. "vitest is green" only ever means the unit and browser projects.
- **`--reporter=basic` is not a valid vitest v4 reporter.** Use the default.
- **`chromadb` is deliberately absent from the bootstrap.** `VectorDBService`
  degrades and warns; the warning is expected output.
- **No live Postgres is needed for the financial suite.**

### Kept from the ledger-screen unit, because the mount still needs it

- **The ledger read defaults to `admitted`** (`transaction_query.py`). Zero rows
  does not mean no financial material; quarantined, superseded and rejected rows
  sit outside the filter. The empty state names the status it filtered on.
- **`total` is `len(transactions)` of the same response.** No paging behind it.
  The panel takes its count from `rows.length` and surfaces a disagreement,
  because the only way the two can differ is a backend that has started paging.
- **Rows arrive ordered by `ordering_date.asc(), row_index.asc()`.** The second
  keeps a statement's own printed sequence where one day holds several movements.
  The table does not sort. **Do not add client-side sorting without dealing with
  that.**
- Three things in the table are correctness, not presentation: an unscaled amount
  is marked, an absent running balance is stated in words rather than left blank,
  and an unrecognised vocabulary member renders loudly with
  `data-unrecognised="true"`.

---

## Build order

The order lives in **`docs/loupe-wiring-plan.md`**, committed as `c88533f`, on
Neil's instruction: "I need you to build everything. Have a think about the best
order and make this the plan and stick to it."

Sixteen units in four phases. One unit per session, finished, tested and committed
before the next begins. **Do not reorder without a ruling.** If a unit turns out
to depend on something later in the list, stop and ask.

- **Phase 1, make rows exist** — precheck endpoint ✅ `a4eb3dc`, ingest endpoint
  ✅ `43f8358`, the interface action on a held file, mount the ledger.
- **Phase 2, make the rows trustworthy** — runs, quarantine, reconciliation,
  adjudication and proof class, duplicates, suspect amounts, locators.
- **Phase 3, make the ledger the source of the graph** — projection, continuity
  and coverage, linkage and correlation and flow.
- **Phase 4, get it out** — exhibit and export, tracing.

**Next unit: Phase 1 item 3, the interface action on a held file.** The two
endpoints exist and nothing in `frontend_v2` calls either of them — confirmed by
grep, zero hits for `financial/ingest` or `financial/precheck` under
`frontend_v2/src`. This unit is what makes them reachable: an action on an
evidence file that prechecks, shows what the file says it holds, and then ingests
on confirmation.

Three things already established that constrain it:

- **It must collect a date range.** `window_start` and `window_end` are required
  query parameters on both endpoints and cannot be defaulted. Two required date
  fields on the dialog, unless Neil rules for storing an engagement period on the
  case instead, which is new schema.
- **It should also offer `default_currency`,** for formats that print none. Both
  endpoints take it, optional. A wrong guess produces amounts that look right,
  which is why it is asked for rather than inferred.
- **Every non-error outcome comes back as a 200 with a word in `outcome`.** The
  dialog has twelve of them to render, not a success path and an error path. The
  full list and what each means is on `IngestOutcome` in
  `services/financial/native_ingest_file.py`.

### Where the old numbering went

Items 1–10a and their commits are unchanged history and stay listed here.

1–7 done through `3784dbe`. 8 done, the Alex description, 1 September. 9 done,
suspect-amount detection, `0910d9f`. 10 done, per-transaction source locator,
`0d6b399`. 10a closed 1 September with no code; triage is out of the build.

11, correction storage, is **still blocked** on the correction-versus-re-ingestion
question below. It maps onto Phase 2 item 10.

12 is absorbed into Phase 1. Both halves of the "both stores" ruling were built
(`de7ef21`, `a9e0d29`), the frontend data layer landed as `fd88318` and the screen
as `94af112`; the mount is Phase 1 item 4 and the ingestion wiring is Phase 1
items 1 to 3, of which two are now done.

13, user-defined view tabs, is **not in the wiring plan** — new capability rather
than connecting built capability, so it stays parked until the plan is worked
through. Two things, not one: named persisted snapshots of filter state, and
exposing source document type onto the transaction row.

14 money movement over time, 15 follow the money: both still parked, both still
new capability rather than wiring. 16 tracing and 17 exhibit tagging are **no
longer parked** — they are Phase 4 of the plan.

---

## Open questions, waiting on Neil

**Was removing `reingest` the right call?** New this session and the most
consequential thing to look at. The reasoning is in full above. Short form: the
override could not succeed for unchanged bytes, and where it could succeed it
would leave two contradictory readings of one file in one case with nothing able
to resolve them until `duplicates.py` is wired at Phase 2 item 9. **Reversible —
say the word and it comes back.**

**The precheck and ingest dialog must collect a date range.** Because the window
cannot be defaulted or derived, the dialog needs two required date fields. The
alternative is storing an engagement period on the case, which is new schema and a
larger decision. **Now live: this is the next unit.**

**Correction versus re-ingestion.** Unchanged, still open, still blocking item 11.
Proposal on the table (a correction triggers a genuine re-run of the balance
identity; only a re-run that closes moves the class), not accepted. **Related to
the `reingest` question above but not the same one** — that one is about reading
the same file twice, this one is about a human editing a stored value.

**Is content-hash de-duplication meant to be call-scoped only?** Still unruled,
and **now live** — `native_ingest_file.py` is the first production caller.
`document_content_hashes` disambiguates duplicate content within one
`record_transactions()` call but not across two separate calls to the same
document. Today the early `already_ingested` refusal means a second call for the
same file does not happen, so nothing depends on the answer yet. That stops being
true the moment an override exists.

**Where does the ledger screen mount?** Still unanswered; Phase 1 item 4. Two
verified facts constrain it: `FinancialPage` early-returns at lines 315 and 323 on
the **Neo4j** query, so a nested tab is unreachable exactly when a freshly
ingested case has ledger rows and no graph — a case that is now actually
producible, since ingestion works; and the persisted `mainView` enum in
`financial.store.ts` has no `version` and no `migrate`, so adding a tab value
needs a migration or it reads a stale persisted value it does not recognise. A
sibling route is the current recommendation. **Its one real cost is two
financial-looking entries in the case sidebar,** where Financial is currently
shortcut 5 of 8.

**Provenance of `exhibit.py`.** Unchanged: confirmed valuable, but it came from a
proposed build order, not a stated Owl requirement.

---

## Standing flags

- **The Postgres ledger now has a production writer, but no interface reaches
  it.** `ingest_native_reading` has exactly one production caller
  (`native_ingest_file.py:331`) and it is reachable over the API, but zero
  frontend files reference `financial/ingest` or `financial/precheck`. So
  `GET /api/financial/ledger` still returns zero rows on every real case until
  someone calls the endpoint by hand or Phase 1 item 3 lands. **Do not let that be
  mistaken for a defect in the screen.**
- **The Neo4j financial view is not a projection of the ledger.** `projection.py`
  has zero production callers. Whatever writes those graph nodes today writes them
  independently, so the two stores can disagree and nothing detects it. Phase 3
  item 12 closes this. **Do not describe the graph as derived from the ledger
  until it is.**
- **Nothing mounts `LedgerPanel` yet.** Two units of frontend work reachable only
  from their tests.
- **No row in the corpus carries a running-balance column.** 30,570 rows across
  325 documents. So on real data **every** row will show "No running balance".
  That is the component working, not failing.
- **P0 is unreachable on the current corpus.** No document carries its own control
  totals in a form that qualifies, so the proof-class badge will never show P0 on
  real material today.
- **Half two has only ever run against synthetic ledgers.**
- **The item-1 geometry machinery IS reached in production** at the
  evidence-engine layer, verified end to end 1 September. Triage is out of the
  build by ruling; do not reopen without a new ruling.
- **The alembic migration `20260902_evidence_table_geometry` has not been applied
  to any real database from a session** — the sandbox has no Postgres. First
  deployment needs an `alembic upgrade head` on Neil's side.

---

## Defects raised and not yet ruled on

Small, real, none blocking:

- `evidence-engine/tests/test_pdf_table_geometry.py::test_the_summary_agrees_with_the_payload_it_summarises`
  fails against current code: it asserts the summary's exact key set without
  `by_table_source`, which `geometry_summary` has emitted since `3784dbe`. A stale
  test, pre-existing.
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
