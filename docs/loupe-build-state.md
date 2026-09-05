# Loupe build state

Where the work stands. Rewritten whenever a unit lands. Durable rules live in
`CLAUDE.md` at the repo root, not here.

**Last updated:** 5 September 2026 (records reconciliation, `dfcef2b`, which
closes Phase 2 item 7)

---

## Position

- **Branch:** `integration/evidence-main-reunion`
- **Head when this was written:** `dfcef2b`
  (`dfcef2bc936d4ddce3457847c2bf386f6bb5a442`), "Run the balance identity across
  a case, and expose the recorded result", parent `53b13b7`.
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
  investigation ten sessions ago. It is **counted in the frontend baseline
  below** (it contributes 1 file and 1 test), so when it is deleted the unit
  numbers drop by one each and that is expected, not a regression.

Also untracked, and **not** mine — Neil's own documents and case material, left
alone. `docs/IP_Protection_Strategy.docx`, `docs/ip-protection-strategy.md`,
`docs/owl-project-brief.md`, and a large amount of Cellebrite and bundle
material at the repo root. **Do not delete any of it to free disk;** see the
disk note under Standing flags.

### Scale

**104 commits** since `c4246c0` (27 August), counting `dfcef2b`; 105 once the
state-file commit lands on top of it. Counted with
`git rev-list --count c4246c0..HEAD`.

`backend/services/financial/` **49 modules** excluding `__init__.py`;
`backend/tests/test_financial_*.py` **56 files**, **3,300 tests**.

### Gate baselines as of `dfcef2b`

- **Backend financial suite: `Ran 3300 tests, OK (skipped=12)`.** Up from 3241 by
  exactly the 59 added this session (45 + 14). **There are no expected
  failures.**
- **Frontend unit: 67 files, 494 tests, all passing.** Unchanged; no frontend
  file was touched this session. 494 includes the stray probe test.
- **`tsc -b` returns 0. `eslint .` returns 0.** Both re-run this session.
- **Frontend browser: NOT RUN this session, and it could not be.** See the disk
  note below. The last known-good figure is 2 files, 4 tests. No frontend file
  changed, so the risk of skipping it here is nil, but **do not carry "browser
  green" forward as though it were verified at this head.**

**Five tracebacks on stderr during the backend run are expected and are not
failures.** One `sqlite3.IntegrityError: UNIQUE constraint failed:
financial_transactions.case_id, financial_transactions.ref_id` prints mid-run
from `tests/test_financial_native_ingest_file.py`, which ingests the same file
twice on purpose. Two more come from `test_financial_quarantine_row.py`, which
injects a `SQLAlchemyError("connection lost")` into each writer to exercise the
`write_failed` path that `quarantine_row.py` logs with `logger.exception`.
**This session adds the last two of the same kind:**
`test_financial_reconcile_case.py` injects an `OperationalError ... locked` on a
liveness `SELECT 1` and a disk-full failure on `COMMIT`, and
`reconcile_case.py` logs both with `logger.exception`. All five are the code
working. **Do not spend a session chasing them.**

---

## What this session did

**Phase 2 item 7, reconciliation, landed as `dfcef2b`.** Seven files, 2,126
insertions, no deletions.

Plan item 7 verbatim: "Whether the rows add up to what the statement printed.
This is the check that says a document was read completely."

### The finding that decided the shape of the unit

**`reconcile_period` has never run in production, and the source says so
plainly.** It is fully written and fully tested, and its only production caller
is `duplicates.py:334` — which itself has no production caller, because
duplicates is Phase 2 item 9 and is not wired. So every
`FinancialStatementPeriod` was created at `not_attempted` (`periods.py:391`) and
stayed there for the life of the case.

Something weaker was standing in for it. `native_ingest.py:249` passes the
**format parser's** verdict about the file to
`documents.reclassify_after_reconciliation`. That is a claim about whether the
file parsed coherently. It is **not** the balance identity over stored, admitted
rows, and after row-level adjudication landed last session the two can diverge
deliberately: quarantining a row changes the second and cannot change the first.

So this unit built the driver that runs the identity across a case's periods and
writes the answer down, plus the read that reports what was written.

### What landed

- **`backend/services/financial/reconcile_case.py`** (546 lines, new). The
  driver `reconcile_period` never had, plus the read. Public surface:
  `PeriodOutcome`, `CaseOutcome`, `PeriodReconciliation`, `CaseReconciliation`,
  `PeriodReconciliationView`, `ReconciliationQueryError`, `reconcile_case`,
  `list_period_reconciliations`, `to_reconciliation_view`.
- **`backend/routers/financial_reconciliation.py`** (191 lines, new). One GET,
  one POST, registered in `routers/__init__.py` and `main.py`.
- **`backend/tests/test_financial_reconcile_case.py`** (1,021 lines, 45 tests,
  new). Real SQLite on disk, real `reconcile_period`, real periods and rows.
- **`backend/tests/test_financial_reconciliation_router.py`** (343 lines, 14
  tests, new). Handlers awaited directly, service mocked, mirroring
  `test_financial_ledger_router.py`.
- **`backend/services/financial/__init__.py`** (+21). Import block and `__all__`
  block for the new module.
- **`backend/main.py`** (+2), **`backend/routers/__init__.py`** (+2).

### The four things the driver has to get right

These are why the driver exists rather than the router calling `reconcile_period`
directly, and each has a named test.

- **A period in another case is not a period.** The sweep is scoped by case, and
  optionally by account, through a join rather than by trusting a caller's id.
- **One bad period cannot abandon the rest.** A period whose stored data will not
  support the arithmetic is reported `refused` with the reason and the sweep
  continues. Its previously recorded verdict is **left untouched rather than
  reset**, because that verdict was a real result when it was taken and a failure
  to re-derive it today is not evidence that it was wrong.
- **A refusal must not leave a number behind.** `reconcile_period` assigns
  `period.reconciliation_status` and only **then** calls `_fits(...)`, which can
  raise `LedgerOverflowError`. So a refusal on that path arrives with a
  half-written verdict already in the session. The driver discards it with
  `session.expire(period)`. **`refresh()` would be wrong**: it autoflushes the bad
  state first, committing the very number being discarded.
- **A read does not recompute.** The GET reports the stored column and nothing
  else, including when the column says `not_attempted`.

### The endpoints

Both under the existing `/api/financial` prefix. **Two routes and two
permissions, which is why this is its own router and not folded into a
neighbour:** `routers/financial_ledger` resolves everything to `case:view` on the
stated grounds that none of its routes write, and the recompute here writes;
`routers/financial_adjudication` resolves everything to `case:edit` on the stated
grounds that all of its routes do, and the read here does not. Either merge would
make an existing module's docstring false.

- `GET /api/financial/reconciliation` — `case:view`. Query: `case_id`
  (required), `account_id`, `reconciliation_status`, `limit`. Response:
  `case_id`, `periods`, `total`.
- `POST /api/financial/reconciliation/run` — `case:edit`. Query: `case_id`
  (required), `account_id`. Response is the sweep whole: `case_id`, `outcome`,
  `applied`, `reason`, `counts`, `total`, `periods`.

**The permission is resolved from the HTTP method, not the path,** so a route
added to this router later inherits the bar its verb implies. A safe method can
only read; anything else is treated as a write whether or not it turns out to be
one, which is the direction a mistake here should fall. Tested for `PUT`,
`PATCH` and `DELETE`, which are not served today.

**`applied` is the flag an interface reads, not the outcome word** — same rule as
`wouldStore`/`didStore` on ingest and `applied` on adjudication, and for the same
reason: a backend one version ahead can send a word this build has never seen.

### Verification

Backend 3241 → 3300, accounted for exactly: 45 in the driver tests and 14 in the
router tests. `tsc -b` 0, `eslint .` 0, unit 67/494 unchanged. Browser project
could not run; see the disk note.

The staged tree (`f44988b8`) was diffed against `HEAD` before committing and held
exactly the seven intended files, with the untracked `.bak` files, the probe test
and all of Neil's case material correctly excluded.

---

## Durable facts, kept so no one rediscovers them

The bootstrap, the baselines, the storybook limitation and the git procedure all
live in **`CLAUDE.md`**. Deliberately not duplicated here.

### New this session

- **`services/financial/__init__.py` re-exports a *function* named
  `reconcile_case`, which shadows the submodule of the same name.** This is a
  live trap for any test that needs the module object:
  `from services.financial import reconcile_case` binds the **function**, so
  `patch.object(that, "reconcile_period")` fails with "does not have the
  attribute". **And the obvious alternative fails identically** —
  `patch("services.financial.reconcile_case.reconcile_period")` resolves a dotted
  target with `getattr` before it falls back to importing, so it hits the same
  function. The working form is
  `import services.financial.reconcile_case` followed by
  `module = sys.modules["services.financial.reconcile_case"]`. **Any future
  module whose name matches one of its own exported callables has this problem.**
- **Use `session.expire(obj)` and never `session.refresh(obj)` to throw away an
  in-flight mutation.** `refresh` autoflushes first, which writes the thing you
  are trying to discard. This matters wherever a service mutates an ORM object
  and then hits a validation that can raise.
- **`reconcile_period` mutates before it validates.** It assigns
  `reconciliation_status` and then calls `_fits(...)`, which raises
  `LedgerOverflowError`. **`MixedCurrencyError` is different** — it is raised
  inside `evaluate_identity`, *before* any mutation. Any caller has to handle
  both, and only one of them leaves state behind.
- **Ordering a period list needs `nullslast()` and a secondary key on `id`.**
  `period_start` is nullable, and NULL ordering differs between SQLite and
  Postgres, so an ordering without it is not portable **and** not total. This is
  the same class of bug as the runs list needing a secondary sort on `id`.
- **`IdentityOutcome`'s field order is `status, totals, opening,
  printed_closing, computed_closing, delta, independent, unavailable_reason`,**
  with properties `is_balanced`, `was_attempted`, and `proves_completeness`
  (balanced **and** independent **and** `totals.is_complete`). Constructing one
  by hand in a test needs all eight.
- **`PeriodBounds` has exactly three constructors:** `printed(start, end)`,
  `derived(start, end)`, `absent()`. `supports_continuity` requires **both**
  bounds be `printed`.
- **`financial_statement_periods` has a second uniqueness rule for the undated
  case.** Beyond
  `uq_financial_statement_periods_document_account_period` on
  `(source_document_id, account_id, period_start, period_end)`, nulls are
  distinct inside a unique constraint, so there is a **partial** index
  `uq_financial_statement_periods_document_account_undated` on
  `(source_document_id, account_id)` `WHERE period_start IS NULL AND period_end
  IS NULL`. A fixture that makes two undated periods for one document and account
  will collide.
- **Four coherence check constraints tie each balance to its source**, of the
  form `(opening_balance_source = 'absent') = (opening_balance_minor IS NULL)`,
  for opening and closing, start and end. A fixture cannot set a source of
  `printed` and leave the amount null.

### From earlier sessions, still true

- **The `playwright install chromium` fix recorded here previously has stopped
  working, and the reason is different from the one it fixed.** The old failure
  was `os.tmpdir()` pointing at the full root filesystem, cured by
  `TMPDIR=/sessions/<session>/tmpdl`. The failure now is that **`/sessions`
  itself is full**: 9.8G total, **129M free** this session, against a 179.6M
  download that then has to extract. It fails with `ENOSPC: no space left on
  device` **after** downloading 100%, twice, once per mirror, so it looks like a
  network problem and is not. **Check `df -h /sessions` before starting the
  install**; if free space is under about 700M the browser gate cannot be run at
  all this session. **The figure is getting worse, not better** — it was 291M
  last session — so assume the gate is unrunnable until measured otherwise.
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
- **`quarantine_row.actor_from_user` builds a `decisions.Actor` from a logged-in
  user.** It uses `getattr` rather than importing the auth model, the same way
  `runs.py` deliberately does, so nothing under `services/financial/` gains a
  dependency on `postgres.models.user`.
- **`_current()` in the quarantine driver reads the row's attributes after
  `session.commit()`.** With `expire_on_commit=True` that triggers a refresh
  round trip. It works and is tested, but it is worth knowing before anyone
  moves the commit.
- **The permission templates define far less than the routers use.**
  `postgres/permissions.py` defines only `case:{view,edit,delete}`,
  `collaborators:{invite,remove}` and `evidence:upload`. **`evidence:process`
  and `evidence:delete` are referenced by existing routers and do not exist in
  the templates at all.** Do not assume a permission string is real because a
  router asks for it.
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
  word.** The same applies to `applied` on the adjudication and reconciliation
  endpoints.
- **An unrecognised vocabulary member is named, never rendered blank,** and **no
  outcome maps to the `default` badge variant** — `Badge` falls through to
  `default` for an unmapped key, so a forgotten member would arrive looking like
  the most important thing on screen.
- **The exports guard is automatic.** `tests/test_financial_exports.py` globs
  `*.py` in the package and asserts each module contributes at least one name to
  `__all__`. A new module needs **no manual list entry**, contrary to the note
  in `CLAUDE.md`. Confirmed again this session: `reconcile_case` was picked up
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
  central fact of this session and of the last one.**
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

### The reconciliation subsystem's own rules

New section. Read it before touching item 6's remaining half or item 8.

- **The identity is `opening + (credits - debits) = closing`, in exact integer
  minor units.** The answer is yes or no, never a score. It is the **only** check
  in the subsystem that can detect a transaction that is simply missing: a
  dropped row does not arrive flagged as doubtful, it does not arrive at all, and
  the printed closing balance is the only witness to it.
- **It declines rather than assumes.** A missing balance gives `unavailable` with
  a reason, never a zero. A zero would make the arithmetic close and would be a
  lie.
- **It counts only `admitted` rows,** and the excluded counts travel with the
  result. This is what makes the identity live: quarantine a row and re-running
  changes the answer.
- **`independent` says whether it proved anything.** An identity computed against
  a balance carried forward from the neighbouring period is arithmetic against
  *that period's figure*, not against this document. Worth having, but not
  evidence that this statement was read completely. `proves_completeness` is
  balanced **and** independent **and** the totals complete.
- **The recompute is a POST and the read is a GET, and the split is load
  bearing.** The stored result is the one recorded against the run that produced
  it, at the time it was produced. If a read recomputed, a figure an analyst
  quoted would be a figure that no longer exists anywhere, and two people opening
  the same case minutes apart could see different arithmetic with nothing to say
  which was which.
- **`not_attempted` is reported, not filtered.** It is the default of the read
  and it is the point of the read: **a ledger nobody has reconciled must not be
  able to present itself as a reconciled one.**
- **A refusal leaves the previously stored verdict alone.** It is not reset to
  `not_attempted`. That verdict was a real result when it was taken, and a
  failure to re-derive it today is not evidence that it was wrong.
- **Nothing here moves a proof class.** Deliberately. Moving a class on this
  result is `assign_proof_class` and `record_admission`, which is Phase 2 item 8.
  Two code paths writing that column on two definitions of the same word is how
  it comes to mean neither.
- **A sweep is safe to run repeatedly.** Re-running after nothing changed
  rewrites the same numbers and a new timestamp.
- **`no_periods` and an all-refused sweep are both `200`.** They are facts about
  the case, and an interface has to render them beside the ledger rather than in
  an error path. Only a failed write is a `500`.
- **The parse-time verdict at `native_ingest.py:249` is a different claim from
  this one** and the two can legitimately disagree. That one is about whether the
  file parsed; this one is about whether the stored, admitted rows add up. **Do
  not reconcile them.**

### The quarantine subsystem's own rules

Read it before touching anything in item 6's remaining half.

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
- **An unchanged row is reported separately from a changed one.** Reporting an
  idempotent no-op as `quarantined` would hand back an `adjudication_id` naming
  **somebody else's earlier decision** as though it were this request's. The
  status is read before the call and that case comes back `unchanged` with no id.
- **The 404 is worded identically for a row in another case and a row that does
  not exist,** so asking cannot be used to learn what a case the caller cannot
  see contains. There is a test asserting the two routes word it the same.

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
  ended. **Adjudication moves rows afterwards**, and **so does a reconciliation
  sweep's effect on what those rows mean**, so they will legitimately disagree
  with a `COUNT(*)` over the ledger today. **Do not reconcile them.**
- **`started_by_email` outlives `started_by_user_id`.** The FK is
  `ON DELETE SET NULL`. Prefer the email.
- **`reap_stale_runs` is global, not case-scoped.** This is why it is a lifespan
  loop and not an endpoint.
- **Ordering runs needs the secondary sort on `id`.** `started_at` alone is not
  a total order. Same rule now applies to ordering periods.

### And on the frontend, as of `dfcef2b`

Unchanged from `bc23570`; no frontend file has been touched for three sessions.

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
  (write path `150084a`); reconciliation ✅ item 7 (`dfcef2b`). Then adjudication
  and proof class, duplicates, suspect amounts, locators.
- **Phase 3, make the ledger the source of the graph** — projection, continuity
  and coverage, linkage and correlation and flow.
- **Phase 4, get it out** — exhibit and export, tracing.

### Next unit: item 6's remaining half. Its blocker is now cleared.

The previous state file recorded that both remaining pieces of item 6 needed
something item 7 produces. **Item 7 has landed, so that dependency is
satisfied** and the work is unblocked:

- **`would_rescue`** and **`QuarantineBasis.from_proof` reached through
  `localise`** both take an `IdentityOutcome`. `IdentityOutcome` is produced by
  `reconcile.evaluate_identity`, which is now driven across a case by
  `reconcile_case` and exposed on two endpoints. Nothing further is needed from a
  later item.
- **The quarantine screen.** It has had a population to draw since `150084a`, and
  its most important column — why a row is held, and whether the arithmetic or a
  person held it — now has two values to distinguish, because computed grounds
  become reachable once `from_proof` is wired.

**Take `would_rescue` and `from_proof` first and the screen second,** in that
order, and treat them as one unit unless the session runs short. The screen's
column is only worth building once there is something in the second value.

### The screen question, settled by reading the source

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

**New: reconciliation is a fourth financial router rather than a route on an
existing one.** Decided by reading the two neighbours' docstrings.
`routers/financial_ledger` states that every route resolves to `case:view`
because none of them writes; the recompute writes.
`routers/financial_adjudication` states that every route resolves to `case:edit`
because all of them do; the read does not. Either merge would make an existing
module's stated rule false. **What would reverse it:** a decision to let a router
carry mixed permissions and drop those docstring claims, which would be a
readability judgement rather than a correctness one and is not worth making now.

**New: the recompute requires `case:edit`, not `evidence:upload`.** Nothing is
added to the case — rows already in the ledger are summed and the answer is
written onto periods already in the ledger. That is the case's own content being
edited, which is the bar the adjudication routes already apply for the same kind
of change. **What would reverse it:** the same new adjudication permission
category that would reverse the adjudication decision below; they should move
together.

**New: the read reports the stored column and never recomputes.** So a period
that has never been checked comes back `not_attempted`, and re-running is an act
a person takes. **What would reverse it:** a demonstrated case where a stale
stored figure is worse than an unstable one. Note the asymmetry — the current
choice is recoverable by pressing a button, and the reverse is not recoverable at
all, because a figure that was quoted and then silently recomputed cannot be got
back.

**New: a refusal during a sweep leaves the stored verdict alone.** It is not
reset to `not_attempted`. **What would reverse it:** evidence that a stale
`balanced` on a period whose data has since become unreadable misleads someone in
practice. The counter-argument, and why the current direction was taken, is that
resetting throws away a real result on the strength of a transient failure.

**The adjudication endpoints require `case:edit`, not `evidence:upload`.**
Decided by reading `postgres/permissions.py`, which defines only
`case:{view,edit,delete}`, `collaborators:{invite,remove}` and
`evidence:upload`. Ingest asks for the evidence permission because it **adds
evidence** to the case. Nothing is added by quarantine or release; an existing
row is moved out of every total or moved back into them, which is the case's own
content being edited. **What would reverse it:** a new permission category for
adjudication, which would be reasonable if Owl ever wants a role that can load
evidence but not change what counts. That is a schema and seeding change, not a
one-line one, and nothing needs it today.

**Quarantine's write path was built before its screen.** Not a resequencing —
item 6 is still item 6 — but a decision about which half of it comes first, taken
because **nothing in production wrote `ledger_status='quarantined'`**, so a
screen built first would have listed an empty set forever. **What would reverse
it:** nothing; the write path is landed. Recorded so the order is not later
mistaken for an oversight.

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

**Whether a correction re-runs the arithmetic: still not decided, and it is now
one item away from being decidable.** The proposal is that a correction re-runs
the balance identity and only a re-run that closes moves the proof class. It has
support in the source: `adjudication.py`'s `restated_opening` (line 332) and
`restatement_delta` (line 357). It is consistent with the settled rule that proof
class is computed and never set by hand. **But it makes a correction an event
that can change how much of a document is trusted, not a local edit.**
Reconciliation is now built, so half the machinery exists and
`reconcile_case(db, case_id, account_id=...)` is the call a correction would
make. **Proof class (item 8) still lands before the correction unit. Decide it
then, from the built code.**

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
- **The balance identity now runs, but only through the API.** Nothing in the
  interface calls either reconciliation endpoint yet, and **nothing calls the
  recompute automatically** — not ingestion, not adjudication. So on a live case
  every period stays `not_attempted` until somebody POSTs to
  `/api/financial/reconciliation/run`. **That is deliberate for this unit** (the
  recompute is an act a person takes) **but it means the read will report
  `not_attempted` everywhere until a caller exists.** Do not read that as a
  defect in the arithmetic.
- **Whether ingestion should trigger a sweep at the end of a run is not
  decided and was not decided here.** It is the obvious next caller, and item 8
  (proof class) is the unit that will actually need one. Flagged, not parked.
- **A row can now be set aside and let back in, but only through the API.**
  Nothing in the interface calls either endpoint yet. Until the screen lands,
  the quarantine population is reachable only via
  `GET /api/financial/ledger?ledger_status=quarantined`, and **the ledger tab's
  own totals silently exclude it**.
- **The Neo4j financial view is not a projection of the ledger.**
  `projection.py` has zero production callers. The two stores can disagree and
  nothing detects it. Phase 3 item 12 closes this. **Do not describe the graph
  as derived from the ledger until it is.** Note that quarantining a row and
  reconciling a period both change the ledger and **do not** touch the graph, so
  this gap now has two more ways to show itself.
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
  That is the component working, not failing. **This bears directly on
  reconciliation:** a period whose balances are absent reconciles `unavailable`,
  not `unbalanced`, and on the current corpus that will be the common answer.
- **P0 is unreachable on the current corpus.** No document carries its own
  control totals in a form that qualifies.
- **Half two has only ever run against synthetic ledgers.**
- **The item-1 geometry machinery IS reached in production** at the
  evidence-engine layer, verified end to end 1 September.
- **The alembic migration `20260902_evidence_table_geometry` has not been
  applied to any real database from a session** — the sandbox has no Postgres.
  First deployment needs an `alembic upgrade head` on Neil's side.
- **Disk: the browser gate may simply be unrunnable in a given session, and it
  is getting worse.** Both filesystems are near full — root at 99%, `/sessions`
  at 99% with **129M free**, down from 291M one session ago — and chromium needs
  roughly 700M to install. **Check `df -h /sessions` first and say plainly if the
  gate cannot run**, rather than reporting a previous session's figure. The repo
  mount has 39G free but is Neil's tree and must not be used as scratch.

---

## Defects raised and not yet ruled on

Small, real, none blocking:

- **`reconcile_period` mutates the period before it validates.** It assigns
  `reconciliation_status` and then calls `_fits(...)`, which can raise
  `LedgerOverflowError`, leaving a half-written verdict in the session.
  `reconcile_case` defends against it with `session.expire(period)` and there is
  a named test for the path, **so nothing is broken today** — but the ordering is
  a trap for the next caller, and the next caller is item 8. **Direction: swap
  the order inside `reconcile_period` when item 8 touches it**, rather than
  making every caller remember to expire.
- **`docs/loupe-wiring-plan.md`'s premise for item 6 is wrong.** It says
  quarantined rows are written today and never shown. Nothing in production ever
  wrote one. **And item 7's premise was wrong in the same way** — the plan
  treats reconciliation as something that runs and needs surfacing, when
  `reconcile_period` had no reachable production caller at all. The plan text is
  left in place as history. **Do not build from those sentences.** Assume other
  items carry the same kind of error: the plan describes intent, and the source
  is what is true.
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
  not defined in `postgres/permissions.py`.** Whether those routes are
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
