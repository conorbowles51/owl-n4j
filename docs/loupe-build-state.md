# Loupe build state

Where the work stands. Rewritten whenever a unit lands. Durable rules live in
`CLAUDE.md` at the repo root, not here.

**Last updated:** 5 September 2026 (records the quarantine write path, `150084a`,
which closes the first half of Phase 2 item 6)

---

## Position

- **Branch:** `integration/evidence-main-reunion`
- **Head when this was written:** `150084a`
  (`150084ab154d6eb5adc624cda78a5f4f9a18010b`), "Financial: adjudicated
  quarantine and release for one stored ledger row", parent `8aef23d`.
  **Confirm the real tip with `git log --oneline -5`** at the start of every
  session rather than trusting this line — the state-file commit that follows
  this one will already have moved it.
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
  investigation nine sessions ago. It is **counted in the frontend baseline
  below** (it contributes 1 file and 1 test), so when it is deleted the unit
  numbers drop by one each and that is expected, not a regression.

Also untracked, and **not** mine — Neil's own documents and case material, left
alone. `docs/IP_Protection_Strategy.docx`, `docs/ip-protection-strategy.md`,
`docs/owl-project-brief.md`, and a large amount of Cellebrite and bundle
material at the repo root. **Do not delete any of it to free disk;** see the
disk note under Standing flags.

### Scale

**102 commits** since `c4246c0` (27 August), counting `150084a`; 103 once the
state-file commit lands on top of it. Counted with
`git rev-list --count c4246c0..HEAD`.

`backend/services/financial/` **48 modules** excluding `__init__.py`;
`backend/tests/test_financial_*.py` **54 files**, **3,241 tests**.

### Gate baselines as of `150084a`

- **Backend financial suite: `Ran 3241 tests, OK (skipped=12)`.** Up from 3201 by
  exactly the 40 added this session (27 + 13). **There are no expected
  failures.**
- **Frontend unit: 67 files, 494 tests, all passing.** Unchanged; no frontend
  file was touched this session. 494 includes the stray probe test.
- **`tsc -b --force` returns 0. `eslint .` returns 0.** Both re-run this session.
- **Frontend browser: NOT RUN this session, and it could not be.** See the disk
  note below. The last known-good figure is 2 files, 4 tests. No frontend file
  changed, so the risk of skipping it here is nil, but **do not carry "browser
  green" forward as though it were verified at this head.**

**One traceback on stderr during the backend run is expected and is not a
failure.** A `sqlite3.IntegrityError: UNIQUE constraint failed:
financial_transactions.case_id, financial_transactions.ref_id` prints mid-run
from `tests/test_financial_native_ingest_file.py`, which ingests the same file
twice on purpose. **This session adds two more of the same kind:**
`test_financial_quarantine_row.py` injects a `SQLAlchemyError("connection
lost")` into each writer to exercise the `write_failed` path, and
`quarantine_row.py` logs it with `logger.exception`, so two more tracebacks now
print. All three are the code working. **Do not spend a session chasing them.**

---

## What this session did

**Phase 2 item 6, quarantine — the write half, landed as `150084a`.** Seven
files, 1,668 insertions, no deletions.

### The finding that decided the shape of the unit

**The wiring plan's premise for item 6 is factually wrong, and the source says
so plainly.** The plan says quarantined rows are written today and never shown,
which implies the missing piece is a screen. It is not.

**Nothing in production ever sets `ledger_status` to `'quarantined'`.**
`quarantine_transaction` and `release_transaction` have existed in
`services/financial/quarantine.py`, fully tested, since they were written, and
**no caller anywhere reaches either of them.** So the population a quarantine
screen would list is empty, and would have stayed empty however well the screen
was built. The screen was not what was missing. A way for a person to put a row
into that state was.

That is why this session built the write path and not the screen, and it is not
a resequencing of the plan: item 6 is still item 6, and its remaining half is
described under Build order below.

### What landed

- **`backend/services/financial/quarantine_row.py`** (389 lines, new). The
  driver those two writers never had. Resolves a row within a case, builds the
  grounds from the person taking the decision, calls the writer, names the
  decision that was appended, commits. Public surface: `RowAdjudicationOutcome`,
  `RowAdjudication`, `ActorError`, `actor_from_user`, `find_case_transaction`,
  `quarantine_case_row`, `release_case_row`.
- **`backend/routers/financial_adjudication.py`** (156 lines, new). Two POST
  routes, registered in `routers/__init__.py` and `main.py`.
- **`backend/tests/test_financial_quarantine_row.py`** (717 lines, 27 tests,
  new). Real SQLite on disk, real writers, real adjudication log.
- **`backend/tests/test_financial_adjudication_router.py`** (385 lines, 13
  tests, new). Handlers awaited directly, service mocked, mirroring
  `test_financial_ledger_router.py`.
- **`backend/services/financial/__init__.py`** (+17). Import block and `__all__`
  block for the new module.
- **`backend/main.py`** (+2), **`backend/routers/__init__.py`** (+2).

### The three things the driver has to get right

These are the reasons the driver exists at all rather than the router calling
`quarantine.py` directly, and each has a named test.

- **A refusal is not an error.** A row already held on computed grounds, a
  superseded row, a blank reason, a user the system cannot name: each is a fact
  about the row's current standing, and the person asking needs to read it
  beside the row rather than in the browser's error path. All of them come back
  as an outcome word on a **200**. Only a row the caller may not see (404) and a
  genuine database fault (500) become error statuses, and **the 404 is worded
  identically for a row in another case and a row that does not exist**, so that
  asking cannot be used to learn what a case the caller cannot see contains.
  There is a test asserting the two routes word it the same.
- **An unchanged row is reported separately from a changed one.**
  `quarantine_transaction` is idempotent for identical grounds: asked twice it
  appends nothing the second time and returns the row. Reporting that as
  `quarantined` would hand back an `adjudication_id` naming **somebody else's
  earlier decision** as though it were this request's. So the status is read
  before the call, and that case is reported as `unchanged` carrying no id at
  all.
- **The person's name reaches the row twice on purpose,** once inside the
  quarantine detail (`QuarantineBasis.from_adjudication` renders
  `f"{actor}: {reason}"`) and once as the actor on the appended decision. The
  row can hold only the first, because
  `ck_financial_transactions_quarantine_coherent` requires a released row to
  carry **no reason at all**. The log is therefore the only place a reversal can
  be recorded, and the two paths have to agree about who took each step. **A
  release is appended after the quarantine it reverses, never in place of it** —
  asserted by comparing `subject_sequence`.

### The endpoints

Both under the existing `/api/financial` prefix, both POST, both `case:edit`:

- `POST /api/financial/transactions/{transaction_id}/quarantine`
- `POST /api/financial/transactions/{transaction_id}/release`

Query: `case_id` (required). Body: `reason` (required, embedded).
Response: `transaction_id`, `outcome`, `applied`, `reason`, `ledger_status`,
`quarantine_reason`, `adjudication_id`.

**`outcome` is one of six words:** `quarantined`, `released`, `unchanged`,
`not_found`, `refused`, `write_failed`. **`applied` is true for exactly two of
them** and is the flag an interface should read, not the word — same rule as
`wouldStore`/`didStore` on the ingest endpoints, and for the same reason: a
backend one version ahead can send a word this build has never seen.

### Verification

Backend 3201 → 3241, accounted for exactly: 27 in the driver tests and 13 in the
router tests. `tsc -b --force` 0, `eslint .` 0, unit 67/494 unchanged. Browser
project could not run; see the disk note.

The staged tree was diffed against `HEAD` before committing and held exactly the
seven intended files, with the untracked `.bak` files, the probe test and all of
Neil's case material correctly excluded.

---

## Durable facts, kept so no one rediscovers them

The bootstrap, the baselines, the storybook limitation and the git procedure all
live in **`CLAUDE.md`**. Deliberately not duplicated here.

### New this session

- **The `playwright install chromium` fix recorded here previously has stopped
  working, and the reason is different from the one it fixed.** The old failure
  was `os.tmpdir()` pointing at the full root filesystem, cured by
  `TMPDIR=/sessions/<session>/tmpdl`. The failure now is that **`/sessions`
  itself is full**: 9.8G total, 291M free, against a 179.6M download that then
  has to extract. It fails with `ENOSPC: no space left on device` **after**
  downloading 100%, twice, once per mirror, so it looks like a network problem
  and is not. **Check `df -h /sessions` before starting the install**; if free
  space is under about 700M the browser gate cannot be run at all this session.
  The session-local directory holds only 163M of that, so there is nothing of
  mine to delete; the rest is not ours to remove.
- **The repo mount is a different, much larger filesystem** —
  `/sessions/<session>/mnt/owl-n4j` is 461G with 39G free — but **do not stage
  the browser download there.** It is Neil's working repo, the workspace denies
  `unlink`, and 350M of undeletable browser binaries would be left in his tree.
- **When only backend files change, say so and skip the browser project rather
  than reporting a stale figure as fresh.** Check with
  `git status --porcelain` before deciding.
- **`quarantine.py`'s two writers return the transaction, not the event.** So
  naming the adjudication that was just appended means reading it back:
  `history(session, transaction, AdjudicationSubject.transaction)[-1]`. Safe
  because `decisions.record` ends in `session.flush()` and `history` orders by
  `subject_sequence`, which is assigned, rather than by `id`, which is a random
  uuid4, or `created_at`, which two rows can share.
- **There was no helper for building a `decisions.Actor` from a logged-in
  user,** and there is now: `quarantine_row.actor_from_user`. It uses `getattr`
  rather than importing the auth model, the same way `runs.py` deliberately
  does, so nothing under `services/financial/` gains a dependency on
  `postgres.models.user`. It drops a non-UUID id so a bad value fails there with
  a readable message instead of at a foreign key far away.
- **`_current()` in the driver reads the row's attributes after
  `session.commit()`.** With `expire_on_commit=True` that triggers a refresh
  round trip. It works and is tested, but it is worth knowing before anyone
  moves the commit.
- **The permission templates define far less than the routers use.**
  `postgres/permissions.py` defines only `case:{view,edit,delete}`,
  `collaborators:{invite,remove}` and `evidence:upload`. **`evidence:process`
  and `evidence:delete` are referenced by existing routers and do not exist in
  the templates at all.** Do not assume a permission string is real because a
  router asks for it.

### From earlier sessions, still true

- **A component that throws for want of a provider does not fail a
  `FinancialPage` test — it vanishes.** Every panel on that page is wrapped in
  its own `ErrorBoundary`, which catches the throw and renders a fallback, so
  the suite stays green while the thing under test is dead. Mock every hook the
  page reaches for, and assert presence explicitly.
- **`tsc -b` alone is not enough after writing test fixtures.** Vitest does not
  typecheck. Use `--force`; the incremental build will otherwise skip a project
  it thinks is current.
- **The git ref file must be `Read` before it can be `Write`n.** `Write` refuses
  with "File has not been read yet" unless that exact path was `Read` earlier in
  the same session. Read it first; its contents are the old head.
- **`Edit`'s read precondition is inconsistent about slices, so do not plan
  around it.** Try a slice on a large file — it may be enough — and fall back to
  a full read rather than assuming either way.
- **The vitest unit project takes about 80 seconds** at 67 files. Not a hang.
- **Never read a "no tests" result as green.** A stale vite cache path, a
  missing chromium and the `unlink` denial all produce it.
- **Radix tab triggers activate on `mousedown`, not `click`.** `fireEvent.click`
  leaves the tab where it was, and **every assertion after it silently describes
  the previous tab** — the test still passes, it just tests the wrong panel.
- **`TooltipProvider` is mounted app-wide at `app/providers.tsx:13`,** so any
  page test rendering a component that uses a tooltip needs one too.
- **A `Transaction` fixture needs six fields minimum.** `BaseFinancialRecord`
  (`financial/api.ts:3–86`) requires `key`, `amount`, `from_entity`,
  `to_entity`, `financial_record_kind`, `financial_view_mode` and
  `is_financial_event`; `TransactionRecord` adds
  `is_evidence_backed_transaction`.
- **A bare account number does not identify an account.** `AccountDraft.observed`
  (`accounts.py:400`) requires an IBAN, a routing number, or an identifier
  **plus an institution name**; otherwise `_account_draft`
  (`native_subjects.py:202`) falls back to `AccountDraft.unidentified` with
  `distinguisher = f"{sha256}:{ordinal}"`. So a BAI2 or MT940 statement that
  prints an account number and names no bank lands **unidentified with the
  number still visible**. **Do not describe the flag as "no account number
  found" anywhere in the interface.**
- **The `distinguisher` is the file's own sha256,** stable across re-reads, so a
  precheck account key equals the key that gets written.
- **The ledger cannot silently double, and it is the schema that guarantees it.**
  `ref_id` is deterministic from `(file sha256, row content)` and
  `uq_financial_transactions_case_ref` is on `(case_id, ref_id)`. **Do not
  restate the old claim that a second run doubles the money; it is wrong.**
- **A failure inside a `with ingestion_run(...)` block must roll back the
  caller's session before it leaves.** Otherwise the open write transaction
  contends with the run's own bookkeeping session, `_terminate_quietly` swallows
  it by design, and the run is left `running`.
- **`IntegrityError` text is not portable.** SQLite names the offending
  **columns**, Postgres names the **constraint**. Assert the table name.
- **`completed_at` cannot be asserted against a literal.** The column is
  `DateTime(timezone=True)`: Postgres returns it with its offset, SQLite returns
  it naive. Assert against the row's own value plus a prefix check.
- **DB-backed financial tests need file-on-disk SQLite, not `:memory:`** — and
  doubly so for anything that runs on a worker thread.
- **`financial_source_documents` is unique on
  `(ingestion_run_id, evidence_file_id)`** — one row per file per run.
- **`evidence_files.stored_path` is `NOT NULL`.** The pathless file that
  production can actually hold is the **empty string**, not `None`.
- **Prefer `ingestion_run` (the context manager) over `open_ingestion_run`.**
- **No module under `services/financial/` imports `config`.** That is why the
  financial tests need no environment. A new module takes its knobs as
  arguments.
- **NACHA yields accounts and no periods.** camt 3/3 rows and a period, BAI2 3/3
  and a period, MT940 2/2 and a period, NACHA 1/1 and **no** period. Junk bytes
  give `unrecognised`.
- **The century window is required and never defaulted.** Max span
  `CENTURY_WINDOW_MAX_SPAN_YEARS = 99`; wider, or backwards, is a 400.
- **A precheck verdict is not a promise the write will succeed.**
  `contradictory_period` and `already_ingested` are decided against rows already
  stored, not against the file.
- **`wouldStore` and `didStore` read the endpoint's flag, never the outcome
  word.** The same now applies to `applied` on the adjudication endpoints.
- **An unrecognised vocabulary member is named, never rendered blank,** and **no
  outcome maps to the `default` badge variant** — `Badge` falls through to
  `default` for an unmapped key, so a forgotten member would arrive looking like
  the most important thing on screen.
- **The exports guard is automatic.** `tests/test_financial_exports.py` globs
  `*.py` in the package and asserts each module contributes at least one name to
  `__all__`. A new module needs **no manual list entry**, contrary to the note
  in `CLAUDE.md`. Confirmed again this session: `quarantine_row` was picked up
  with no edit to that file.
- **Every Bash command needs its own absolute `cd`.** Where a `cd` is awkward,
  `PYTHONPATH=<abs>/backend` works for one-liners.
- **Any scratch file in `/tmp` needs a per-user name,** including the git index,
  the vite cache, and any file used only to capture output.
- **`GIT_INDEX_FILE` does not survive between Bash invocations.** Staging and
  `git write-tree` must happen in one command. `commit-tree` can be a second
  command **provided it passes the tree hash you already verified.** A commit
  message with awkward punctuation is safest passed with `-F <file>`.
- **A compound `cmd; echo "exit: $?"` inside a longer `&&` chain can report an
  empty exit code**, and `$?` after a pipe is the pipe's status.
- **`&&`-chaining a `grep` that finds nothing silently kills the rest of the
  line.** Use `;` between verification steps.
- **`backend/venv/` poisons every repo-wide grep.** Always pass
  `--exclude-dir=venv --exclude-dir=__pycache__`, and `--exclude-dir=tests` when
  the question is whether something is wired in production.
- **Counting bare name occurrences does not tell you whether something is
  reached.** Grep for the import and list the files. **This is what found the
  central fact of this session.**
- **The house component-test conventions** are `render`/`screen` from
  `@testing-library/react`, `MemoryRouter`/`Routes`/`Route` for a routed page,
  `vi.hoisted` for a mock that has to capture something, `data-testid` for
  anything a test needs to find, and `fireEvent` never `userEvent`.
- **Radix `DialogContent` renders a corner X carrying an `sr-only` "Close",** so
  a footer button named "Close" makes `getByRole` ambiguous. Tell them apart by
  `data-slot="dialog-close"`. Related: **`TooltipTrigger asChild` overwrites the
  child's `data-slot`**, so a badge inside a tooltip is found by `data-variant`.
- **`Badge` spreads `React.ComponentProps<"span">`.** Variants are `default`,
  `secondary`, `destructive`, `outline`, `success`, `danger`, `warning`, `info`,
  `amber`, `slate`.
- **`tsconfig` has `strict: true` but not `noUncheckedIndexedAccess`.**
- **React Query is `^5.90.21`**, so `isPending`, not `isLoading`.
- **Any new code touching `amount_minor` must use `formatLedgerAmount`,** whose
  `currency` parameter is a **required `string`**.
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

### The quarantine subsystem's own rules

New section. Read it before touching anything in item 6's remaining half.

- **Grounds are a proof or a person, and nothing else.** `QuarantineBasis` has
  three constructors and **none of them takes a `Candidate`**, by design. A
  class a person can raise must not be able to pass for one the arithmetic
  proved, which is the settled rule that proof class is computed and never set
  by hand. The endpoints therefore always record `QuarantineReason.adjudicated`
  and the computed grounds are unreachable from HTTP.
- **`ck_financial_transactions_quarantine_coherent` is
  `(quarantine_reason IS NOT NULL) = (ledger_status = 'quarantined')`.** A
  released row **must** have its reason nulled, so a row that was quarantined
  and let back in is, on the row alone, indistinguishable from one that was
  never held. **The adjudication log is the only place that history exists.**
  Anything reporting on quarantine has to read the log, not the row.
- **`quarantine_transaction` refuses a row that is not `admitted`.** So a
  superseded or rejected row cannot be quarantined, and the driver reports that
  as `refused` with the writer's own words.
- **`quarantine_transaction` is idempotent for identical grounds and refuses
  different ones.** Same grounds: returns the row, appends nothing. Different
  grounds: raises `UngroundedQuarantineError` containing "already quarantined".
  The refusal is deliberate — it stops a person's opinion overwriting a computed
  class.
- **`release_transaction` refuses a row that is not quarantined** with a message
  containing "nothing to release", and requires both a real `Actor` and a
  non-empty reason.

### The ledger screen's own rules

- **The ledger read defaults to `admitted`** (`transaction_query.py`). Zero rows
  does not mean no financial material; quarantined, superseded and rejected rows
  sit outside the filter. The empty state names the status it filtered on.
- **`total` is `len(transactions)` of the same response.** No paging behind it.
  The panel takes its count from `rows.length` and surfaces a disagreement.
- **Rows arrive ordered by `ordering_date.asc(), row_index.asc()`.** The table
  does not sort. **Do not add client-side sorting without dealing with that.**
- Three things in the table are correctness, not presentation: an unscaled
  amount is marked, an absent running balance is stated in words rather than
  left blank, and an unrecognised vocabulary member renders loudly with
  `data-unrecognised="true"`.
- **The ledger query key is `["financial-ledger", caseId, ...]`,** deliberately
  outside `["financial", caseId, ...]`. `useIngestFile` invalidates the former
  only.

### The runs subsystem's own rules

- **`GET /api/financial/runs` returns every status by default,** the opposite of
  the ledger read. Anything built on top must not "helpfully" filter to
  completed runs; the failures are the payload.
- **The run read makes no staleness judgement, and must not start.** Deciding a
  run is abandoned is the reaper's call and the reaper writes it down.
- **The counts on a run are historical.** `documents_seen`,
  `transactions_admitted` and `transactions_quarantined` were true when the run
  ended. **Adjudication moves rows afterwards** — and as of this session there
  is finally a path that does — so they will legitimately disagree with a
  `COUNT(*)` over the ledger today. **Do not reconcile them.**
- **`started_by_email` outlives `started_by_user_id`.** The FK is
  `ON DELETE SET NULL`. Prefer the email.
- **`reap_stale_runs` is global, not case-scoped.** This is why it is a lifespan
  loop and not an endpoint.
- **Ordering runs needs the secondary sort on `id`.** `started_at` alone is not
  a total order.

### And on the frontend, as of `150084a`

Unchanged from `bc23570`; no frontend file was touched this session.

- **`readRunStatus(raw).needsAttention`** is true for `pending`, `running`,
  `failed`, `aborted`, and **false for an unrecognised status**, deliberately,
  with a named test.
- **`RUN_COUNTS_ARE_HISTORY` must accompany the three counts** wherever they are
  shown; `IngestionRunsTable` renders it itself so a caller cannot separate them.
- **`readRunStarter` prefers the email**, falls back to `User <id>`, and says
  "Not recorded" rather than rendering an empty cell.
- **`formatRunTime` is fixed to `en-GB`,** matching `formatLedgerAmount`. An
  unparseable value is shown as it arrived, not as "Invalid Date".
- **`runDuration` returns `null` rather than `0`,** with two distinct
  presentations keyed `run-no-end` and `run-no-duration`. Do not collapse them.
- **`IngestionRunNotice` calls `useIngestionRuns(caseId)` with no params,** so
  its cache entry is `["financial-runs", caseId, null]`. **Anything else wanting
  every attempt on the case must call it the same way** or it opens a second
  cache entry and a second request for identical data.
- **The runs query key is outside both other keys, and nothing invalidates it.**
  Ruled closed by Neil.
- **The notice is a sibling of `LedgerPanel`, not inside it.** `LedgerPanel`'s
  four early returns would otherwise hide it exactly when the ledger is empty.
  **Do not "tidy" this by nesting them.**
- **`FinancialMainView` has five members**, `"ledger" | "runs" | "transactions"
  | "counterparties" | "trends"`. **The order is load bearing:** the first two
  read Postgres, the last three read the graph.
- **The ledger and attempts tabs take no graph chrome.** A case with an empty
  graph must still reach both.
- **`api.runs.test.ts` reads the Python source** to prove the two languages
  still agree. A backend change to the route, the parameters, the envelope keys
  or the ordering clause fails a frontend test. That is the intended alarm.

---

## Build order

The order lives in **`docs/loupe-wiring-plan.md`**, committed as `c88533f`, on
Neil's instruction: "I need you to build everything. Have a think about the best
order and make this the plan and stick to it."

Sixteen units in four phases. One unit per session, finished, tested and
committed before the next begins. **Do not reorder without a ruling.** If a unit
turns out to depend on something later in the list, stop and ask.

- **Phase 1, make rows exist — COMPLETE.** Precheck endpoint ✅ `a4eb3dc`,
  ingest endpoint ✅ `43f8358`, the interface action on a held file ✅ `17d94ac`,
  mount the ledger ✅ `4324b24`.
- **Phase 2, make the rows trustworthy** — runs ✅ item 5 complete (backend
  `cde43c5`, notice `8924668`, attempts list `bc23570`); quarantine **half done**
  (write path `150084a`). Then reconciliation, adjudication and proof class,
  duplicates, suspect amounts, locators.
- **Phase 3, make the ledger the source of the graph** — projection, continuity
  and coverage, linkage and correlation and flow.
- **Phase 4, get it out** — exhibit and export, tracing.

### Item 6's remaining half, and why it is not next

Two pieces are left, and **both of them need something from item 7**:

- **`would_rescue`** and **`QuarantineBasis.from_proof` reached through
  `localise`** both take an `IdentityOutcome`, which is produced by `reconcile`.
  Reconciliation **is** Phase 2 item 7. Building them now would mean building
  item 7 first under item 6's name, which is the resequencing the working
  agreement forbids.
- **The quarantine screen.** It now has a population to draw, but it will draw a
  much more useful one once computed quarantine exists, and its most important
  column — why a row is held, and whether the arithmetic or a person held it —
  only has two values to distinguish after item 7.

**Next unit: Phase 2 item 7, reconciliation.** Item 6's remaining half follows it
directly, and should be picked up as the session after, not folded into item 7.

### The screen question, settled by reading the source

The previous state file asked whether quarantine should be its own tab or a
filter on the ledger tab, and said the source could settle it. It does:

- **The read is the same endpoint.** `GET /api/financial/ledger` already takes
  `ledger_status`, and `ledger_status=quarantined` returns exactly the
  quarantined population. **No new read endpoint is needed and none was built.**
- **But a quarantined row carries a field an admitted row structurally cannot.**
  `quarantine_reason` is non-null for exactly the quarantined rows and null for
  everything else, guaranteed by the check constraint. A column that is
  meaningful for one status and structurally empty for every other is a column
  that does not belong in the shared table.
- **So: a filter on the read, a distinct presentation on the screen.**
  `FinancialMainView` gaining a sixth member is the likely shape, placed with the
  first two because it reads Postgres. **This is a recommendation, not a
  commitment** — the unit that builds it should confirm against
  `LedgerTable.tsx` whether a conditional column is cheaper than a second table.

### Where the old numbering went

Items 1–10a and their commits are unchanged history and stay listed here.

1–7 done through `3784dbe`. 8 done, the Alex description, 1 September. 9 done,
suspect-amount detection, `0910d9f`. 10 done, per-transaction source locator,
`0d6b399`. 10a closed 1 September with no code; triage is out of the build.

11, correction storage, **is no longer blocked.** It maps onto Phase 2 item 10,
and the direction is settled in Standing decisions below.

12 is absorbed into Phase 1, which is now complete.

13, user-defined view tabs, is **not in the wiring plan** — new capability
rather than connecting built capability, so it stays parked. Two things, not
one: named persisted snapshots of filter state, and exposing source document
type onto the transaction row. **This interacts with a decision already
taken:** the financial page no longer persists which tab you were on.

14 money movement over time, 15 follow the money: both still parked, both still
new capability rather than wiring. 16 tracing and 17 exhibit tagging are **no
longer parked** — they are Phase 4 of the plan.

---

## Standing decisions, and what would reverse each one

**This section is not a queue of questions for Neil.** By standing instruction, a
session does not open by asking him to rule on things. Every entry below states
the direction the build takes by default, so a session can proceed without a
conversation. Each one also says exactly what evidence or instruction would
reverse it. Raise one with Neil only when the unit in front of you actually
turns on it, and then raise it oriented and with a recommendation.

**New: the adjudication endpoints require `case:edit`, not `evidence:upload`.**
Decided by reading `postgres/permissions.py`, which defines only
`case:{view,edit,delete}`, `collaborators:{invite,remove}` and
`evidence:upload`. Ingest asks for the evidence permission because it **adds
evidence** to the case. Nothing is added by quarantine or release; an existing
row is moved out of every total or moved back into them, which is the case's own
content being edited. `case:edit` is denied to a viewer and granted to an editor
and an owner, and `routers/financial.py` already requires it to write the graph.
**What would reverse it:** a new permission category for adjudication, which
would be reasonable if Owl ever wants a role that can load evidence but not
change what counts. That is a schema and seeding change, not a one-line one, and
nothing needs it today.

**New: quarantine's write path was built before its screen.** Not a
resequencing — item 6 is still item 6 — but a decision about which half of it
comes first, taken because **nothing in production writes
`ledger_status='quarantined'`**, so a screen built first would list an empty set
forever. **What would reverse it:** nothing; the write path is landed. Recorded
so the order is not later mistaken for an oversight.

**Correction storage: a correction inserts a replacement row, it does not edit
the row.** This is the direction for Phase 2 item 10, and item 11 of the old
numbering is unblocked by it. Researched on 5 September by reading the source.

- **The relational ledger has no correction columns at all.** Verified against
  `postgres/models/financial.py`: no `amount_corrected`, no `original_amount`,
  no `correction_reason`. What it has is supersession —
  `ledger_status IN ('admitted', 'quarantined', 'superseded', 'rejected')` with
  `superseded_by_id` on `FinancialTransaction` (line 807) and the same pair on
  `FinancialSourceDocument` (line 321). The model docstring at line 21 states
  the intended behaviour outright.
- **Corrections today happen only on the graph side**, in
  `services/neo4j/financial_service.py:599`, `update_transaction_amount`. That
  is edit-in-place, and it is the competing design. It is not wrong for the
  graph; `projection.py` lists those properties in `USER_OWNED_PROPERTIES` and
  refuses to write them, so a projection run cannot undo a person's work.
- **The citation reference decides it.** `references.py` computes the reference a
  report cites a row by from the row's content, deliberately, so a row whose
  figure changed gets a new one. Under supersession that falls out for free.
  Under edit-in-place the reference either changes underneath a report that
  already cited it, or is frozen and then names a figure it was not computed
  from. `ref_id` also carries `UniqueConstraint("case_id", "ref_id")`, so the
  two designs collide rather than merely differ.
- **The cost, stated honestly:** two rows exist for one corrected transaction,
  and every reader of the ledger has to be status-aware. The ledger endpoint
  already defaults to `admitted`, so existing readers are correct by default;
  new ones are the risk.
- **What would reverse it:** an instruction from Neil, or a downstream unit that
  genuinely cannot work across a supersession pair. The graph's edit-in-place
  path is not evidence against it — the graph is not the ledger.

**Whether a correction re-runs the arithmetic: not yet decided, and it does not
need to be yet.** The proposal is that a correction re-runs the balance identity
and only a re-run that closes moves the proof class. It has support in the
source: `adjudication.py`'s `restated_opening` (line 332) and
`restatement_delta` (line 357). It is consistent with the settled rule that
proof class is computed and never set by hand. **But it makes a correction an
event that can change how much of a document is trusted, not a local edit.**
Reconciliation (item 7) and proof class (item 8) both land before the correction
unit. **Decide it then, from the built code, not now.**

**Removing `reingest` stands.** The override could not succeed for unchanged
bytes, and where it could succeed it would leave two contradictory readings of
one file in one case with nothing able to resolve them until `duplicates.py` is
wired at Phase 2 item 9. **Reversible at any time and cheap to reverse** — item
9 is the natural moment to revisit it.

**Content-hash de-duplication stays call-scoped.** `document_content_hashes`
disambiguates duplicate content within one `record_transactions()` call and not
across two calls. **What would reverse it:** an override existing. If `reingest`
comes back, this has to be answered in the same session, not after.

**The engagement period stays off the case.** The dialog asks for the window
every time. If a case ever grows a date range, the dialog **defaults from it and
keeps asking** rather than stopping, because a file can legitimately fall
outside the engagement period and the reader has to be able to say so.

**`exhibit.py` stays in the plan at Phase 4 item 15.** Its provenance is a
proposed build order rather than a stated Owl requirement, and that is recorded
so nobody later mistakes it for a requirement Neil gave.

**The financial page will say nothing about the two stores disagreeing until
Phase 3 item 12.** Explaining a disagreement before the thing that removes it is
built means shipping an explanation with a short life. **What would reverse
it:** a real case where the two visibly disagree in front of an investigator
before item 12 lands.

---

## Standing flags

- **Phase 1 is closed: a bank file can be sent to the ledger from seven places
  and the rows it creates are now visible.**
- **A row can now be set aside and let back in, but only through the API.**
  Nothing in the interface calls either endpoint yet. Until the screen lands,
  the quarantine population is reachable only via
  `GET /api/financial/ledger?ledger_status=quarantined`, and **the ledger tab's
  own totals silently exclude it**, which is the same behaviour as before —
  except that from this commit the excluded set can actually be non-empty.
- **The Neo4j financial view is not a projection of the ledger.**
  `projection.py` has zero production callers. The two stores can disagree and
  nothing detects it. Phase 3 item 12 closes this. **Do not describe the graph
  as derived from the ledger until it is.** Note that quarantining a row changes
  the ledger and **does not** touch the graph, so this gap just got one more way
  to show itself.
- **A run whose process died is now closed, but only by the loop.** Six hours
  stale, five minute interval. **Until it fires, a dead run and a live one are
  indistinguishable through the API**, deliberately: the read declines to guess.
  The threshold is a knob (`FINANCIAL_RUN_STALE_AFTER_HOURS`).
- **The notice is only on the ledger tab, and the attempts list only on its
  own.** Deliberate for now, because the other three tabs read the graph, but it
  stops being defensible at Phase 3 item 12. **Revisit the mounting then.**
- **Nothing on screen explains that the tab strip spans two stores.** Deliberate
  and already ruled. Listed only so it is not rediscovered as an oversight.
- **No row in the corpus carries a running-balance column.** 30,570 rows across
  325 documents. So on real data **every** row will show "No running balance".
  That is the component working, not failing.
- **P0 is unreachable on the current corpus.** No document carries its own
  control totals in a form that qualifies.
- **Half two has only ever run against synthetic ledgers.**
- **The item-1 geometry machinery IS reached in production** at the
  evidence-engine layer, verified end to end 1 September.
- **The alembic migration `20260902_evidence_table_geometry` has not been
  applied to any real database from a session** — the sandbox has no Postgres.
  First deployment needs an `alembic upgrade head` on Neil's side.
- **Disk: the browser gate may simply be unrunnable in a given session.** Both
  filesystems are near full — root at 99%, `/sessions` at 97% with 291M free —
  and chromium needs roughly 700M to install. **Check `df -h /sessions` first
  and say plainly if the gate cannot run**, rather than reporting a previous
  session's figure. The repo mount has 39G free but is Neil's tree and must not
  be used as scratch.

---

## Defects raised and not yet ruled on

Small, real, none blocking:

- **`docs/loupe-wiring-plan.md`'s premise for item 6 is wrong.** It says
  quarantined rows are written today and never shown. Nothing in production ever
  wrote one. Found and acted on this session; the plan text is left in place as
  history. **Do not build from that sentence.** It is worth assuming other items
  carry the same kind of error: the plan describes intent, and the source is
  what is true.
- **The graph's correction path takes the new amount as a `float`.**
  `services/neo4j/financial_service.py:599`. The ledger side handles money
  exactly through `Money`, so a corrected figure entered on the graph and a
  total computed from the ledger can disagree at the cent. **Direction: fix it
  as part of Phase 2 item 10.** If anything starts relying on graph corrections
  before then, fix it immediately instead.
- **`IngestionRunHandle.terminate()` does not check the row's stored status.** A
  run the reaper closed as `failed` that then turns out to be alive and finishes
  will overwrite the status with `completed` **while leaving the reaper's
  abandonment text in `run.error`.** **If the six-hour threshold is ever
  lowered, fix this first.**
- **`evidence:process` and `evidence:delete` are asked for by routers and are
  not defined in `postgres/permissions.py`.** Found this session while settling
  the permission bar. Not investigated further; whether those routes are
  therefore open, closed, or handled elsewhere was not established, and it
  should be before anyone relies on them.
- `evidence-engine/tests/test_pdf_table_geometry.py::test_the_summary_agrees_with_the_payload_it_summarises`
  fails against current code: it asserts the summary's exact key set without
  `by_table_source`, which `geometry_summary` has emitted since `3784dbe`.
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
  sweep footer prose into the table chunk. Geometry unaffected; full diagnosis
  in the `72d1b1a` revision of this file.
- **`docs/loupe-wiring-plan.md` lines 117–123 are superseded** by the work and by
  two rulings. Left in place as history; do not act on them.
- **The wiring plan names `_cleanup_stale_chunks` as the loop shape to copy.**
  It is the wrong precedent (no error handling); `poll_forever` is the right one.
