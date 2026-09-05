# Loupe build state

Where the work stands. Rewritten whenever a unit lands. Durable rules live in
`CLAUDE.md` at the repo root, not here.

**Last updated:** 5 September 2026 (records the precheck endpoint, `a4eb3dc`)

---

## Position

- **Branch:** `integration/evidence-main-reunion`
- **Head when this was written:** `a4eb3dc`
  (`a4eb3dcefb84ded604280c6ba43f9f8ba76b133e`), "Read a bank file and report what
  it holds, before deciding to store it", parent `5cd8827`. **Confirm the real tip
  with `git log --oneline -5`** at the start of every session rather than trusting
  this line.
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
  investigation four sessions ago. It is **counted in the frontend baseline
  below** (it contributes 1 file and 1 test), so when it is deleted the unit
  numbers drop by one each and that is expected, not a regression.

### Scale

81 commits since `c4246c0` (27 August), counting `a4eb3dc`.

Measured this session, after the commit:
`backend/services/financial/` **45 modules**, **33,158 lines**;
`backend/tests/test_financial_*.py` **49 files**, **3,103 tests**.

### Gate baselines as of `a4eb3dc`

- **Backend financial suite: `Ran 3103 tests, OK (skipped=12)`.** Up from 3,057.
  The 46 new tests are exactly the two new files (34 service, 12 router). Skipped
  is unchanged at 12. **There are no expected failures.**
- **Frontend unit: 58 files, 354 tests, all passing.** The `CLAUDE.md` figure of
  54/285 predates the ledger-screen unit and is stale; 354 includes the stray
  probe test.
- **Frontend browser: 2 files, 4 tests.** `tsc -b` returns 0. `eslint .` returns 0.

---

## What this session did

**Phase 1 item 1 of the wiring plan: the precheck endpoint.** Committed as
`a4eb3dc`, seven files, 1,534 insertions, no deletions.

`POST /api/financial/precheck` opens one evidence file, detects its format, parses
it and describes the accounts, periods and balances it claims, then returns that
description. It stores nothing, opens no ingestion run and leaves no trace on the
case, so it can be called before the person has decided anything. It is the
reading half of the seam that `native_ingest.py` describes; the write half is the
next unit.

### What landed

- **`backend/services/financial/native_precheck.py`** (675 lines). The service.
  `PrecheckOutcome` (7 members), frozen dataclasses `PrecheckBalance`,
  `PrecheckPeriod`, `PrecheckAccount`, `SkippedRow`, `FilePrecheck`, and four
  entry points layered `precheck_reading` → `precheck_bytes` → `precheck_path` →
  `precheck_case_file`.
- **`backend/routers/financial_ingest.py`** (129 lines). A **new** router, not an
  addition to `financial_ledger.py`.
- **`backend/services/financial/__init__.py`**, **`routers/__init__.py`**,
  **`main.py`** — exports and registration.
- **`backend/tests/test_financial_native_precheck.py`** (34 tests) and
  **`backend/tests/test_financial_ingest_router.py`** (12 tests).

### Decisions taken, and the evidence for each

**The century window is required and never defaulted.** Three of the four native
formats print two-digit years and none carries the century, so something has to
say which hundred years the evidence falls in. Checked, not assumed: grep for
`CenturyWindow(` across `backend/` excluding `venv`, `__pycache__` and `tests`
returns **zero production constructions** — this router is the first caller in the
tree, so there is no existing convention to copy. The `Case` model carries
`id, title, description, status, archived, created_by_user_id, owner_user_id` and
**no date range** to derive one from. The class docstring
(`native.py:235`) says the window is "Supplied by the caller because the document
does not contain it". A default would decide a statement's decade silently in the
one place the document gives no help. **`window_start` and `window_end` are
required query parameters, so the dialog in Phase 1 item 3 must collect the
engagement period.** Max span is `CENTURY_WINDOW_MAX_SPAN_YEARS = 99`; wider, or
backwards, is a 400.

**Only `not_found` becomes an error status.** A file belonging to another case is
reported identically to one that does not exist, so asking cannot be used to learn
what an unreadable case contains. Every other failing outcome returns **200** with
the description attached, because an unparseable statement is a fact about the
evidence that belongs on the screen beside the files that read cleanly, not in the
browser's error path. `test_an_unreadable_file_is_a_200_describing_it` subTests all
five and is the assertion that fails against the tempting implementation where
anything other than `readable` raises.

**A new router rather than `financial_ledger`.** That module's docstring states
that none of its routes write and its permission resolver resolves everything to
`("case", "view")` on those grounds. The ingest route that is the next unit does
write and needs `evidence:upload`, so putting it there would make that docstring
false. Both share the `/api/financial` prefix; a test asserts they are distinct
routers with the same prefix. The resolver here already carries the comment
explaining that it will have to distinguish the two by path.

### Two corrections made while writing the tests

**A dead exception handler, removed.** `precheck_reading` caught
`DateResolutionError`. It cannot reach that frame: `native_subjects._yymmdd`
(line 167) swallows it and returns `None`, and it has only two call sites (325,
403). The behaviour that matters is the reason it is swallowed — an unresolvable
date on a *printed balance* is recorded as an absent bound rather than discarding
the statement, its rows and its amounts over its own header. Only a **row** date
can raise, and that happens inside `read_native` one level up. The branch is gone,
the `out_of_window` docstring now says where the outcome actually comes from, and
`test_the_dead_window_branch_stays_dead` fails if it returns.

**A wrong explanation of `identified`, rewritten.** The smoke test showed BAI2 and
MT940 reporting `identified=False` while plainly printing an account number, which
contradicted what the docstring claimed. Rather than assume the fixture was odd,
this was reproduced directly:
`AccountDraft.observed(identifier_as_printed="1234567890")` raises
`AccountIdentityError: nothing in this draft identifies an account`. Adding
`institution_name="B"` makes it succeed. The flag was structurally right; the prose
was wrong. See the durable fact below.

### Verification

Both gates run green and are recorded above. The backend suite went 3,057 → 3,103
with skipped unchanged, and 46 is exactly the two new files, which confirms nothing
else moved. The frontend gate was run for completeness; no frontend file was
touched this session.

---

## Durable facts, kept so no one rediscovers them

The bootstrap, the baselines, the `VITE_CACHE_DIR` requirement, the playwright
install, the storybook limitation and the git procedure all live in
**`CLAUDE.md`**. Deliberately not duplicated here.

### New this session

- **A bare account number does not identify an account.** `AccountDraft.observed`
  (`accounts.py:400`) calls `draft.identity()` eagerly and requires an IBAN, a
  routing number, or an identifier **plus an institution name**. Otherwise it
  raises `AccountIdentityError` and `_account_draft` (`native_subjects.py:202`)
  falls back to `AccountDraft.unidentified`, which sets
  `distinguisher = f"{sha256}:{ordinal}"`. So a BAI2 or MT940 statement that prints
  an account number and names no bank lands **unidentified with the number still
  visible**. `identified=False` therefore does **not** mean no number was printed.
  What it costs is joining: those movements cannot be recognised as the same
  account in another document until the institution is established. **Do not
  describe the flag as "no account number found" anywhere in the interface.**
- **The `distinguisher` is the file's own sha256.** Stable across re-reads, unique
  across documents, and ingestion computes it the same way — so a precheck account
  key equals the key that would be written. Pinned by
  `test_the_distinguisher_is_the_rows_own_hash`.
- **NACHA yields accounts and no periods.** It is not a statement: it names the
  *receiver's* account per entry, prints no balances and states no period. Verified
  by smoke test across all four formats — camt 3/3 rows and a period, BAI2 3/3 and
  a period, MT940 2/2 and a period, NACHA 1/1 and **no** period. Junk bytes give
  `unrecognised`.
- **Reuse the shared fixture builders in `tests/test_financial_native.py`** rather
  than writing new ones: `WINDOW`, `camt_bytes(**kwargs)`, `bai2_bytes(**overrides)`,
  `mt940_bytes(**overrides)`, `nacha_bytes(records)`, `NACHA_SIMPLE`. Note that
  `nacha_bytes` takes a **required positional** `records`, unlike the other three.
- **The exports guard is automatic.** `tests/test_financial_exports.py` globs `*.py`
  in the package and asserts each module contributes at least one name to `__all__`.
  A new module needs **no manual list entry**, contrary to the note in `CLAUDE.md`.
- **A precheck verdict is not a promise the write will succeed.** A period that
  contradicts one already stored is decided against the database, not against the
  file, and cannot be known at precheck time. `would_ingest` is shorthand for one
  value of `outcome`, nothing more.
- **Turn a stray traceback in test output into an assertion.** `logger.exception`
  in the service polluted the run; wrapping the case in
  `assertLogs(native_precheck.logger, level="ERROR")` removed the noise **and**
  pinned a real property — the caller gets a clean verdict while the engineer keeps
  the stack. Note the router test deliberately does *not* assert its one-line 500
  log, matching `test_financial_ledger_router.py`.
- **Router tests await the handler directly and patch the service.** No test
  client. `test_financial_ledger_router.py` is the exemplar and the new file mirrors
  it deliberately, including the module-level `patch.object(financial_ingest, ...)`
  form, which only works because the router imports the service function by name.

### Carried forward, still true

- **Every Bash command needs its own absolute `cd`.** Broken twice two sessions
  ago: once it worked by luck, the second time it ran `grep` in the wrong directory
  and **hung for the full two minute timeout**, which does not look like a missing
  `cd` at all.
- **Any scratch file in `/tmp` needs a per-user name.** `/tmp` is sticky and the
  sandbox user changes every session; a plain `/tmp/tsc.out` from an earlier session
  is owned by another uid and a redirect into it fails with `Permission denied`,
  which looks exactly like the command having failed. Use
  `/tmp/<name>-$(id -un).<ext>` for everything, **including the git index**.
- **`GIT_INDEX_FILE` does not survive between Bash invocations.** Staging and
  `git write-tree` must happen in one command. The `commit-tree` can be a second
  command **provided it re-exports `GIT_INDEX_FILE` and passes the tree hash you
  already verified** — that is what was done this session and it worked.
- **`&&`-chaining a `grep` that finds nothing silently kills the rest of the
  line.** `grep` exits 1 on no match. Use `;` between verification steps.
- **`backend/venv/` poisons every repo-wide grep.** Always pass
  `--exclude-dir=venv --exclude-dir=__pycache__`, and `--exclude-dir=tests` when the
  question is whether something is wired in production.
- **Counting bare name occurrences does not tell you whether a component is
  mounted.** Grep for `import .*\bName\b` and list the files.
- **`ast` plus `grep` is a cheap and reliable wiring audit.** Watch for exported
  symbols that are ordinary English words; they need reading by eye.
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
- **Verify a `lucide-react` export before importing it.** `node -e` against the
  package is a two-second check.
- **No shared money formatter existed before the data-layer unit.** Other financial
  components use `toLocaleString("en-US", ...)` on a float — those are Neo4j-backed
  `Transaction` rows, which carry floats, so they are not wrong today. Any new code
  touching `amount_minor` must use `formatLedgerAmount` and nothing else.
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
  `test_financial_transaction_query` builds SQLite in a temp directory.

### Kept from the ledger-screen unit, because the mount still needs it

- **The ledger read defaults to `admitted`** (`transaction_query.py`). Zero rows
  does not mean no financial material; quarantined, superseded and rejected rows sit
  outside the filter. The empty state names the status it filtered on.
- **`total` is `len(transactions)` of the same response.** No paging behind it. The
  panel takes its count from `rows.length` and surfaces a disagreement, because the
  only way the two can differ is a backend that has started paging.
- **Rows arrive ordered by `ordering_date.asc(), row_index.asc()`.** The second keeps
  a statement's own printed sequence where one day holds several movements. The table
  does not sort. **Do not add client-side sorting without dealing with that.**
- Three things in the table are correctness, not presentation: an unscaled amount is
  marked (`formatLedgerAmount` returning `scaled: false` shows 123456 where 1,234.56
  belongs), an absent running balance is stated in words rather than left blank, and
  an unrecognised vocabulary member renders loudly with `data-unrecognised="true"`.

---

## Build order

The order lives in **`docs/loupe-wiring-plan.md`**, committed as `c88533f`, on
Neil's instruction: "I need you to build everything. Have a think about the best
order and make this the plan and stick to it."

Sixteen units in four phases. One unit per session, finished, tested and committed
before the next begins. **Do not reorder without a ruling.** If a unit turns out to
depend on something later in the list, stop and ask.

- **Phase 1, make rows exist** — precheck endpoint ✅ `a4eb3dc`, ingest endpoint,
  the interface action on a held file, mount the ledger. Nothing in the other three
  phases can be verified against real data until this lands.
- **Phase 2, make the rows trustworthy** — runs, quarantine, reconciliation,
  adjudication and proof class, duplicates, suspect amounts, locators.
- **Phase 3, make the ledger the source of the graph** — projection, continuity and
  coverage, linkage and correlation and flow.
- **Phase 4, get it out** — exhibit and export, tracing.

**Next unit: Phase 1 item 2, the ingest endpoint.** A POST on
`routers/financial_ingest.py` that calls `ingest_native_reading`
(`services/financial/native_ingest.py:165`), which today has zero production
callers. It **writes**, so it needs `evidence:upload` and
`_ingest_case_permission` has to start distinguishing routes by path — the comment
in the resolver already says so. It should take the same window and currency
parameters as the precheck route, for the same reasons.

### Where the old numbering went

Items 1–10a and their commits are unchanged history and stay listed here.

1–7 done through `3784dbe`. 8 done, the Alex description, 1 September. 9 done,
suspect-amount detection, `0910d9f`. 10 done, per-transaction source locator,
`0d6b399`. 10a closed 1 September with no code; triage is out of the build.

11, correction storage, is **still blocked** on the correction-versus-re-ingestion
question below. It maps onto Phase 2 item 10.

12 is absorbed into Phase 1. Both halves of the "both stores" ruling were built
(`de7ef21`, `a9e0d29`), the frontend data layer landed as `fd88318` and the screen
as `94af112`; the mount is Phase 1 item 4 and the ingestion wiring, which was
always the larger piece, is Phase 1 items 1 to 3.

13, user-defined view tabs, is **not in the wiring plan** — it is new capability
rather than connecting built capability, so it stays parked here until the plan is
worked through. Two things, not one: named persisted snapshots of filter state, and
exposing source document type onto the transaction row.

14 money movement over time, 15 follow the money: both still parked, both still new
capability rather than wiring. 16 tracing and 17 exhibit tagging are **no longer
parked** — they are Phase 4 of the plan.

---

## Open questions, waiting on Neil

**The precheck dialog must collect a date range.** Not a question so much as a
consequence Neil should see before Phase 1 item 3 is designed: because the window
cannot be defaulted or derived, the dialog needs two date fields, and they are
required. The alternative is storing an engagement period on the case, which is new
schema and a larger decision. **Flagged, not decided.**

**Correction versus re-ingestion.** Unchanged, still open, still blocking item 11.
Proposal on the table (a correction triggers a genuine re-run of the balance
identity; only a re-run that closes moves the class), not accepted.

**Is content-hash de-duplication meant to be call-scoped only?** Still unruled.
`document_content_hashes` disambiguates duplicate content within one
`record_transactions()` call but not across two separate calls to the same
document. This becomes live at Phase 1 item 2, since that is the first production
caller.

**Where does the ledger screen mount?** Still unanswered; it is Phase 1 item 4.
Two verified facts constrain it: `FinancialPage` early-returns at lines 315 and 323
on the **Neo4j** query, so a nested tab is unreachable exactly when a freshly
ingested case has ledger rows and no graph; and the persisted `mainView` enum in
`financial.store.ts` has no `version` and no `migrate`, so adding a tab value needs
a migration or it reads a stale persisted value it does not recognise. A sibling
route is the current recommendation. **Its one real cost is two financial-looking
entries in the case sidebar,** where Financial is currently shortcut 5 of 8.

**Should the precheck dialog be built as the design describes it?** The endpoint
now exists, so the question narrows to the interface. Still inferred from a
docstring rather than from an existing caller.

**Provenance of `exhibit.py`.** Unchanged: confirmed valuable, but it came from a
proposed build order, not a stated Owl requirement.

---

## Standing flags

- **The Postgres ledger still has no production writer.** The precheck endpoint
  reads and stores nothing, so this is unchanged until Phase 1 item 2 lands.
  `ingest_native_reading` has no caller outside its own test file,
  `record_transactions` is reachable only through it, and no POST ingests. Until
  then `GET /api/financial/ledger` returns zero rows on every real case and the
  ledger screen draws its empty state wherever it is mounted. **Do not let that be
  mistaken for a defect in the screen.**
- **The Neo4j financial view is not a projection of the ledger.** `projection.py`
  has zero production callers. Whatever writes those graph nodes today writes them
  independently, so the two stores can disagree and nothing detects it. Phase 3
  item 12 closes this. **Do not describe the graph as derived from the ledger until
  it is.**
- **Nothing mounts `LedgerPanel` yet.** Two units of frontend work are reachable
  only from their tests.
- **No row in the corpus carries a running-balance column.** 30,570 rows across
  325 documents. So on real data **every** row will show "No running balance".
  That is the component working, not failing.
- **P0 is unreachable on the current corpus.** No document carries its own
  control totals in a form that qualifies. The proof-class badge will therefore
  never show P0 on real material today.
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
