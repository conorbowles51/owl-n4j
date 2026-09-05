# Loupe build state

Where the work stands. Rewritten whenever a unit lands. Durable rules live in
`CLAUDE.md` at the repo root, not here.

**Last updated:** 5 September 2026 (records the runs data layer, `cde43c5`)

---

## Position

- **Branch:** `integration/evidence-main-reunion`
- **Head when this was written:** `cde43c5`
  (`cde43c5f43e1558f063020eb6925a6ef2821703f`), "Read the ingestion runs from the
  frontend", parent `7d2ff98`.
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
  investigation eight sessions ago. It is **counted in the frontend baseline
  below** (it contributes 1 file and 1 test), so when it is deleted the unit
  numbers drop by one each and that is expected, not a regression.

Also untracked, and **not** mine — Neil's own documents, left alone:
`docs/IP_Protection_Strategy.docx`, `docs/ip-protection-strategy.md`,
`docs/owl-project-brief.md`.

### Scale

95 commits since `c4246c0` (27 August), counting `cde43c5`.

`backend/services/financial/` **48 modules**;
`backend/tests/test_financial_*.py` **52 files**, **3,201 tests**.

### Gate baselines as of `cde43c5`

- **Backend financial suite: `Ran 3201 tests, OK (skipped=12)`.** Unchanged and
  **not re-run this session** — no backend file was touched. **There are no
  expected failures.**
- **Frontend unit: 64 files, 437 tests, all passing.** Up from 62/405. The delta
  is exactly the two new test files: 14 in `api.runs.test.ts`, 18 in
  `lib/run-format.test.ts`. 437 includes the stray probe test.
- **Frontend browser: 2 files, 4 tests — run and green,** after installing
  chromium, which is a per-session step. **`CLAUDE.md` now carries the corrected
  frontend gate commands**; use them as written.
- **`tsc -b --force` returns 0. `eslint .` returns 0.**

**One traceback on stderr during the backend run is expected and is not a
failure.** A `sqlite3.IntegrityError: UNIQUE constraint failed:
financial_transactions.case_id, financial_transactions.ref_id` prints mid-run.
`tests/test_financial_native_ingest_file.py` ingests the same file twice on
purpose; `native_ingest_file.py:376` catches `SQLAlchemyError`, logs it with
`logger.exception` — which is what puts the traceback on screen — and returns
`write_failed`. **Do not spend a session chasing it.**

---

## What this session did

**Phase 2 item 5, the frontend half.** The backend was finished two commits ago
(`11ff36e` the read, `21687c0` the reaper). Nothing in the interface called the
endpoint, so a failed or half-finished ingest was invisible on screen.

Split into two commits, matching how the backend half landed. **The first has
landed; the second has not been started.**

- `cde43c5` — **the data layer.** Six files, 785 insertions.
- *(not yet written)* — the screen. See "Next unit".

### What landed this commit

- **`frontend_v2/src/features/financial/api.ts`** (+116). The runs types
  (`INGESTION_RUN_STATUSES`, `IngestionRunStatus`, `IngestionRun`,
  `INGESTION_RUN_FIELDS`, `IngestionRunsResponse`) and
  `financialAPI.getIngestionRuns`.
- **`lib/run-format.ts`** (185 lines, new). Turns a run row into English.
- **`hooks/use-ingestion-runs.ts`** (45 lines, new).
- **`api.runs.test.ts`** (239 lines, 14 tests, new).
- **`lib/run-format.test.ts`** (189 lines, 18 tests, new).
- **`CLAUDE.md`** (+11). The orientation rule, below.

### The rule added to `CLAUDE.md`, and why

Neil's words, after the third bad opening question in a row: *"Jesus every
session starts the same. You just bring stuff up out of context and give zero
explanation and do no research,"* then *"You do this every single session."*

The structural cause is in this file. **`docs/loupe-build-state.md` is written
for the next session to resume from. It is not a briefing for Neil and he has
not read it.** Opening a continued session in this file's register — item
numbers, module names, words like "runs" and "reaper" used as if shared —
produces a question he cannot answer without opening a file, which is a badly
asked question.

The rule is now a standing instruction under "Working agreement", not a promise.
**Anyone resuming a session should read it before writing the first message.**

### Decisions taken, each from the source rather than invented

- **`if (params.limit !== undefined)`, not `if (params.limit)`.** The falsy form
  swallows `limit: 0` and returns every run to a caller who asked for none. The
  backend refuses 0 with a 400, which is the answer that caller should get.
  There is a named test.
- **`getIngestionRuns` sends no status of its own when none was asked for.** A
  default here could drift from the endpoint's, and the first rows a drifted
  default would hide are the failed ones. Tested on both sides of the wire: the
  request carries only `case_id`, and the router still declares
  `status: Optional[str] = Query(None, ...)`.
- **`needsAttention` is false for an unrecognised status.** True for `pending`,
  `running`, `failed` and `aborted` — every ending that left the ledger holding
  less than the evidence handed to it. An unknown word may name a perfectly
  ordinary ending; raising an alarm about it would report a problem this build
  has no grounds to claim.
- **`failed` and `aborted` keep distinct labels and descriptions** ("Broke" and
  "Stopped"). The backend keeps them separate on purpose; collapsing them on
  screen would hide whether a person decided an incomplete ledger or a fault
  caused it.
- **Narrowing goes through `ledger-format.ts`'s `narrow`,** not a second
  implementation, so an unknown status is named and marked the same way it is
  everywhere else. `RUN_STATUS_VARIANT` is a `Record<IngestionRunStatus, ...>`
  so a forgotten member is a compile error rather than a `default` badge.
- **The frontend mirrors the backend's three refusals** in
  `run-format.ts`'s docstring and in tests: no staleness judgement, no
  reconciliation of the counts, no ranking of runs. This is to stop the screen
  drifting into forming a second opinion the backend deliberately declines to
  form.
- **`RUN_COUNTS_ARE_HISTORY` is one exported string,** so the sentence on screen
  and the sentence the test asserts cannot drift apart.
- **No polling in the hook.** Matches the ledger. How often a half-finished
  ingest is worth a request has not been settled, and an interval would be that
  decision taken silently.
- **Its own query key, `["financial-runs", caseId, params]`.** Neither read
  invalidates the other: refetching the ledger does not change what an attempt
  recorded when it ended.

### Verification

Unit 405 → 437, matching the two new files exactly (14 + 18). Browser 2/4 green.
`tsc -b --force` 0, `eslint .` 0. Backend not re-run: no backend file touched.

### Carried forward from the sessions before

- **The reaper** (`run_reaper.py`, lifespan loop, six hours stale / five minute
  interval) closes a run whose process died. It copies
  `platform_update_service.poll_forever`, **not** `_cleanup_stale_chunks`, which
  the wiring plan wrongly named and which has no error handling at all.
- **No module under `services/financial/` imports `config`.** That is why the
  financial tests need no environment. A new module takes its knobs as
  arguments.
- The ledger screen is mounted as the first of four peer tabs on
  `FinancialPage`, and the page always opens on it.
- **Stopping tab persistence took two mechanisms.** Dropping `mainView` from
  `partialize` stops a choice being written; it does not stop one already
  written being read. An explicit `merge` deletes `mainView` from the persisted
  object and keeps the rest.
- The graph's two early returns moved inside the graph tabs, so a case with
  ledger rows and no graph no longer renders a full-page empty state with no
  tabs.

---

## Durable facts, kept so no one rediscovers them

The bootstrap, the baselines, the playwright install, the storybook limitation and
the git procedure all live in **`CLAUDE.md`**. Deliberately not duplicated here.

### The `CLAUDE.md` frontend section was wrong; it is fixed

It hardcoded `VITE_CACHE_DIR=/tmp/vite-cache` (no user suffix), carried a unit
baseline three sessions stale (54/285), and treated `npx playwright install
chromium` as a one-off rather than a per-session step. **All three produce the
identical symptom: a clean-looking "no tests".** Corrected in the same commit as
this file, along with a line saying never to read "no tests" as green. **The
frontend gate commands in `CLAUDE.md` can now be copied as written.**

Note the unit project tolerates a shared cache path and only the browser project
fails on it, so a green unit run says nothing about the cache being usable.

### New this session

- **The git ref file must be `Read` before it can be `Write`n.** The last step
  of the commit procedure updates
  `.git/refs/heads/integration/evidence-main-reunion` by writing the new sha
  into it. `Write` refuses with "File has not been read yet" unless that exact
  path was `Read` earlier in the same session. Read it first; its contents are
  the old head, which is worth seeing anyway.
- **`Edit` on a large file needs the file read in full, not in slices.** Reading
  `api.ts` with `offset`/`limit` does not satisfy the precondition, and the
  refusal does not say why.
- **The vitest unit project takes about 75 seconds** at 64 files. Not a hang.

### From earlier sessions, still true

- **The `ENOSPC` that once blocked the browser gate is fixable,** by staging the
  playwright download on `/sessions`. **The command now lives in `CLAUDE.md`**
  and is not repeated here. The reason it is needed: `os.tmpdir()` is `/tmp` on
  the **root** filesystem, which is 99% full, while the browsers path is on
  `/sessions`. Check both with `df -h /sessions` and `df -h /tmp` before
  concluding anything about space.
- **Radix tab triggers activate on `mousedown`, not `click`.** `activationMode`
  defaults to `"automatic"`, the trigger carries `onMouseDown` and `onFocus`,
  and **there is no `onClick`**. `fireEvent.click` leaves the tab where it was,
  and **every assertion after it silently describes the previous tab** — the
  test still passes, it just tests the wrong panel. Use `fireEvent.mouseDown`.
- **`TooltipProvider` is mounted app-wide at `app/providers.tsx:13`,** so any
  page test rendering a component that uses a tooltip needs one too. Without it
  the component throws into its own `ErrorBoundary`, **which catches it, so the
  test passes** while asserting against a caught error.
- **Vitest does not typecheck.** Run `tsc -b --force` after writing test
  fixtures, not just after writing product code.
- **A `Transaction` fixture needs six fields minimum.** `BaseFinancialRecord`
  (`financial/api.ts:3–86`) requires `key`, `amount`, `from_entity`,
  `to_entity`, `financial_record_kind`, `financial_view_mode` and
  `is_financial_event`; `TransactionRecord` adds
  `is_evidence_backed_transaction`.
- **A bare account number does not identify an account.** `AccountDraft.observed`
  (`accounts.py:400`) requires an IBAN, a routing number, or an identifier **plus
  an institution name**; otherwise `_account_draft` (`native_subjects.py:202`)
  falls back to `AccountDraft.unidentified` with
  `distinguisher = f"{sha256}:{ordinal}"`. So a BAI2 or MT940 statement that
  prints an account number and names no bank lands **unidentified with the number
  still visible**. **Do not describe the flag as "no account number found"
  anywhere in the interface.**
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
  doubly so for anything that runs on a worker thread, which an in-memory
  connection refuses outright.
- **`financial_source_documents` is unique on
  `(ingestion_run_id, evidence_file_id)`** — one row per file per run.
- **`evidence_files.stored_path` is `NOT NULL`.** The pathless file that
  production can actually hold is the **empty string**, not `None`.
- **Prefer `ingestion_run` (the context manager) over `open_ingestion_run`.**
- **NACHA yields accounts and no periods.** It is not a statement. camt 3/3 rows
  and a period, BAI2 3/3 and a period, MT940 2/2 and a period, NACHA 1/1 and
  **no** period. Junk bytes give `unrecognised`.
- **The century window is required and never defaulted.** Max span
  `CENTURY_WINDOW_MAX_SPAN_YEARS = 99`; wider, or backwards, is a 400.
- **A precheck verdict is not a promise the write will succeed.**
  `contradictory_period` and `already_ingested` are decided against rows already
  stored, not against the file.
- **`wouldStore` and `didStore` read the endpoint's flag, never the outcome
  word.** A backend one version ahead sends a word this build has never seen.
- **An unrecognised vocabulary member is named, never rendered blank,** and **no
  outcome maps to the `default` badge variant** — `Badge` falls through to
  `default` for an unmapped key, so a forgotten member would arrive looking like
  the most important thing on screen.
- **A held file is not necessarily a ledger file.** `blocksDocumentProcessing`
  covers four outcomes; `belongsToLedger` covers one.
- **The exports guard is automatic.** `tests/test_financial_exports.py` globs
  `*.py` in the package and asserts each module contributes at least one name to
  `__all__`. A new module needs **no manual list entry**, contrary to the note in
  `CLAUDE.md`.
- **Every Bash command needs its own absolute `cd`.** Where a `cd` is awkward,
  `PYTHONPATH=<abs>/backend` works for one-liners.
- **Any scratch file in `/tmp` needs a per-user name,** including the git index
  and the vite cache.
- **`GIT_INDEX_FILE` does not survive between Bash invocations.** Staging and
  `git write-tree` must happen in one command. `commit-tree` can be a second
  command **provided it passes the tree hash you already verified.**
- **A compound `cmd; echo "exit: $?"` inside a longer `&&` chain can report an
  empty exit code**, and `$?` after a pipe is the pipe's status. Redirect to a
  per-user file and check separately.
- **`&&`-chaining a `grep` that finds nothing silently kills the rest of the
  line.** Use `;` between verification steps.
- **`backend/venv/` poisons every repo-wide grep.** Always pass
  `--exclude-dir=venv --exclude-dir=__pycache__`, and `--exclude-dir=tests` when
  the question is whether something is wired in production.
- **Counting bare name occurrences does not tell you whether a component is
  mounted.** Grep for `import .*\bName\b` and list the files.
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

### The ledger screen's own rules

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
- **The ledger query key is `["financial-ledger", caseId, ...]`,** deliberately
  outside `["financial", caseId, ...]`, because a graph mutation cannot change a
  relational ledger row. `useIngestFile` invalidates the former only.

### The runs subsystem's own rules

- **`GET /api/financial/runs` returns every status by default,** the opposite of
  the ledger read. Anything built on top must not "helpfully" filter to
  completed runs; the failures are the payload.
- **The run read makes no staleness judgement, and must not start.** A `running`
  row is reported as `running` with the time it started. Deciding a run is
  abandoned is the reaper's call and the reaper writes it down; a reader forming
  the same opinion independently would have no record behind it and the two
  would diverge the moment either threshold moved. **An interface showing a
  running run has to say what it actually knows** — when it started, not that it
  is currently working.
- **The counts on a run are historical.** `documents_seen`,
  `transactions_admitted` and `transactions_quarantined` were true when the run
  ended. Adjudication moves rows afterwards, so they will legitimately disagree
  with a `COUNT(*)` over the ledger today. **Do not reconcile them.**
- **`started_by_email` outlives `started_by_user_id`.** The FK is
  `ON DELETE SET NULL`; the email column is plain. Anything displaying an actor
  should prefer the email.
- **`reap_stale_runs` is global, not case-scoped.** `runs.py:422` selects every
  `running` row across every case with no case filter. **This is why it is a
  lifespan loop and not an endpoint.**
- **Ordering runs needs the secondary sort on `id`.** `started_at` alone is not a
  total order and a case can hold two runs opened within one recorded moment.
  Without the tiebreak the same query answers differently on two calls.

### And on the frontend, as of `cde43c5`

- **`readRunStatus(raw).needsAttention` is the one signal that puts a run in
  front of a reader who did not ask for it.** True for `pending`, `running`,
  `failed`, `aborted`. **False for an unrecognised status** — deliberately, and
  there is a named test. Anything deciding whether to speak up should read this
  rather than test the status word itself.
- **`RUN_COUNTS_ARE_HISTORY` is the sentence that must accompany the three
  counts** wherever they are shown. It is exported from `lib/run-format.ts` so
  the screen and the test cannot drift.
- **`readRunStarter` prefers the email**, falls back to `User <id>`, and says
  "Not recorded" rather than rendering an empty cell, which would read as nobody
  having started the run.
- **`formatRunTime` is fixed to `en-GB`, not the browser's locale**, matching
  `formatLedgerAmount`, so two people reading the same case see the same run. An
  unparseable value is shown **as it arrived**, not as "Invalid Date", which
  keeps the fault attributable to the record.
- **`runDuration` returns `null` rather than `0`** for a run that has not ended,
  for timestamps that disagree, and for a time it cannot parse. Zero would read
  as a run that did nothing instantly.
- **The runs query key is `["financial-runs", caseId, params]`**, outside both
  `["financial-ledger", ...]` and `["financial", ...]`. Nothing invalidates it
  yet; `useIngestFile` does not, and whether it should is an open question for
  the screen pass.
- **`api.runs.test.ts` reads the Python source** to prove the two languages still
  agree: the route decorator and prefix, the three parameter names, the
  every-status default, the envelope keys, `RunView.to_json`'s field set against
  `INGESTION_RUN_FIELDS`, the `IngestionRunStatus` members, and the
  `started_at.desc(), id.asc()` ordering clause. **A backend change to any of
  those fails a frontend test**, which is the intended alarm.

---

## Build order

The order lives in **`docs/loupe-wiring-plan.md`**, committed as `c88533f`, on
Neil's instruction: "I need you to build everything. Have a think about the best
order and make this the plan and stick to it."

Sixteen units in four phases. One unit per session, finished, tested and committed
before the next begins. **Do not reorder without a ruling.** If a unit turns out
to depend on something later in the list, stop and ask.

- **Phase 1, make rows exist — COMPLETE.** Precheck endpoint ✅ `a4eb3dc`,
  ingest endpoint ✅ `43f8358`, the interface action on a held file ✅ `17d94ac`,
  mount the ledger ✅ `4324b24`.
- **Phase 2, make the rows trustworthy** — runs (**item 5, backend complete,
  frontend data layer complete, no screen yet**), quarantine, reconciliation,
  adjudication and proof class, duplicates, suspect amounts, locators.
- **Phase 3, make the ledger the source of the graph** — projection, continuity
  and coverage, linkage and correlation and flow.
- **Phase 4, get it out** — exhibit and export, tracing.

**Next unit: the runs screen, closing item 5. Then item 6, quarantine.**

Everything the screen needs now exists and is tested: `useIngestionRuns`,
`readRunStatus` with `needsAttention`, `readRunStarter`, `formatRunTime`,
`runDuration`, `RUN_COUNTS_ARE_HISTORY`. **What remains is rendering, mounting
and component tests.**

The shape agreed before the data layer was written, and not yet built:

1. **A short notice that speaks only when something needs saying** — a run
   failed, was stopped, or is still open. Driven by `needsAttention`.
2. **A full history of attempts for the case**, most likely a fifth tab, which
   would need a new member on `FinancialMainView` in `stores/financial.store.ts`.

**The notice must be a sibling of `LedgerPanel`, not a child.**
`LedgerPanel.tsx` has **four early returns** — no `caseId`, `isPending`,
`isError`, and `rows.length === 0` — so anything mounted inside it disappears
exactly when the ledger is empty, which is precisely the moment a failed run is
the explanation. Mount it in the ledger `TabsContent` in `FinancialPage.tsx`,
above the panel.

Two things to settle during that pass rather than drift into:

- **Whether `useIngestFile` should invalidate `["financial-runs", ...]`.** It
  invalidates the ledger key only. An ingest creates a run, so the runs list is
  stale immediately after one, but the ledger read has the same property and
  chose not to poll.
- **What the notice says for `pending` and `running`.** `needsAttention` is true
  for both, but neither is a failure, and the run read makes no staleness
  judgement — so the wording has to report a start time and claim nothing about
  whether work is happening.

### Where the old numbering went

Items 1–10a and their commits are unchanged history and stay listed here.

1–7 done through `3784dbe`. 8 done, the Alex description, 1 September. 9 done,
suspect-amount detection, `0910d9f`. 10 done, per-transaction source locator,
`0d6b399`. 10a closed 1 September with no code; triage is out of the build.

11, correction storage, is **still blocked** on the correction-versus-re-ingestion
question below. It maps onto Phase 2 item 10.

12 is absorbed into Phase 1, which is now complete. Both halves of the "both
stores" ruling were built (`de7ef21`, `a9e0d29`), the frontend data layer landed
as `fd88318`, the screen as `94af112`, and the mount as `4324b24`.

13, user-defined view tabs, is **not in the wiring plan** — new capability rather
than connecting built capability, so it stays parked until the plan is worked
through. Two things, not one: named persisted snapshots of filter state, and
exposing source document type onto the transaction row. **This interacts with a
decision already taken:** the financial page no longer persists which tab you
were on, so if user-defined tabs are ever built, the question of what is
remembered across visits has to be reopened deliberately rather than inherited.

14 money movement over time, 15 follow the money: both still parked, both still
new capability rather than wiring. 16 tracing and 17 exhibit tagging are **no
longer parked** — they are Phase 4 of the plan.

---

## Open questions, waiting on Neil

**Was removing `reingest` the right call?** Raised three sessions ago, still
unruled. Short form: the override could not succeed for unchanged bytes, and
where it could succeed it would leave two contradictory readings of one file in
one case with nothing able to resolve them until `duplicates.py` is wired at
Phase 2 item 9. **Reversible — say the word and it comes back.** The send dialog
has no override either, for the same reason: it reports `already_ingested`
plainly and offers nothing to force past it.

**Correction versus re-ingestion.** Unchanged, still open, still blocking item 11.
Proposal on the table (a correction triggers a genuine re-run of the balance
identity; only a re-run that closes moves the class), not accepted. **Related to
the `reingest` question above but not the same one** — that one is about reading
the same file twice, this one is about a human editing a stored value.

**Is content-hash de-duplication meant to be call-scoped only?** Still unruled.
`document_content_hashes` disambiguates duplicate content within one
`record_transactions()` call but not across two separate calls to the same
document. Today the early `already_ingested` refusal means a second call for the
same file does not happen, so nothing depends on the answer yet. That stops being
true the moment an override exists.

**Should the engagement period live on the case?** **Answered by construction for
now, not by ruling:** the dialog asks for the window every time, because the
alternative is new schema. If a case ever grows a date range, the dialog should
default from it rather than stop asking, since a file can legitimately fall
outside the engagement period and the reader has to be able to say so.

**Provenance of `exhibit.py`.** Unchanged: confirmed valuable, but it came from a
proposed build order, not a stated Owl requirement.

**Should the financial page say anything about the two stores disagreeing?** See
the standing flag below. Raised, unruled.

---

## Standing flags

- **Phase 1 is closed: a bank file can be sent to the ledger from seven places
  and the rows it creates are now visible.**
- **The Neo4j financial view is not a projection of the ledger.** `projection.py`
  has zero production callers. Whatever writes those graph nodes today writes them
  independently, so the two stores can disagree and nothing detects it. Phase 3
  item 12 closes this. **Do not describe the graph as derived from the ledger
  until it is.** The financial page now shows both stores side by side in one tab
  strip, which makes a disagreement visible to a reader for the first time, and
  nothing in the interface explains it.
- **A run whose process died is now closed, but only by the loop.** The reaper
  runs every five minutes and closes anything `running` for more than six hours.
  **Until it fires, a dead run and a live one are still indistinguishable
  through the API**, and that is deliberate: the read declines to guess. Six
  hours is a long time to look wrong, and the number is a knob
  (`FINANCIAL_RUN_STALE_AFTER_HOURS`) precisely so it can be lowered once real
  run durations are known.
- **A failed or half-finished run is still invisible on screen.** Still true
  after `cde43c5`. The endpoint returns them and the frontend can now read,
  narrow and phrase them — but **nothing renders any of it**: no component
  imports `useIngestionRuns` or `run-format.ts`. This is the remaining half of
  item 5 and it is the next thing to build.
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
- **The root filesystem is at 99% but `/sessions` is not, and the browser gate
  runs fine.** See Durable facts for the `TMPDIR` fix for `playwright install`.

---

## Defects raised and not yet ruled on

Small, real, none blocking:

- **`IngestionRunHandle.terminate()` does not check the row's stored status.**
  Found this session by reading `runs.py`. It guards only on the in-process
  `self._closed` flag, then unconditionally assigns `run.status`. So a run the
  reaper closed as `failed` — because its process looked dead — that then turns
  out to be alive and finishes will overwrite the status with `completed`
  **while leaving the reaper's "Abandoned: no terminal status was recorded
  within ..." text sitting in `run.error`.** The result is a row that says it
  completed and carries an abandonment message. Not fixed: it is outside the
  wiring plan's item 5 and the six-hour threshold makes it very unlikely. **If
  the threshold is ever lowered, fix this first.**
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
- **`docs/loupe-wiring-plan.md` lines 117–123 are now superseded** by the work and
  by two rulings. Left in place as history; do not act on them.
- **The wiring plan names `_cleanup_stale_chunks` as the loop shape to copy.**
  It is the wrong precedent (no error handling); `poll_forever` is the right one.
  Superseded by this session's work.
