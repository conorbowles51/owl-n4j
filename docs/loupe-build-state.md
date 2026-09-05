# Loupe build state

Where the work stands. Rewritten whenever a unit lands. Durable rules live in
`CLAUDE.md` at the repo root, not here.

**Last updated:** 5 September 2026 (records the ledger mount, `4324b24`)

---

## Position

- **Branch:** `integration/evidence-main-reunion`
- **Head when this was written:** `4324b24`
  (`4324b247eac11da2320b14be9bc17f37d8c046e4`), "Mount the ledger on the
  financial page, as the tab it opens on", parent `f6e3617`. **Confirm the real
  tip with `git log --oneline -5`** at the start of every session rather than
  trusting this line.
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
  investigation seven sessions ago. It is **counted in the frontend baseline
  below** (it contributes 1 file and 1 test), so when it is deleted the unit
  numbers drop by one each and that is expected, not a regression.

Also untracked, and **not** mine — Neil's own documents, left alone:
`docs/IP_Protection_Strategy.docx`, `docs/ip-protection-strategy.md`,
`docs/owl-project-brief.md`.

### Scale

89 commits since `c4246c0` (27 August), counting `4324b24`.

Backend untouched this session: `backend/services/financial/` **46 modules**,
**33,759 lines**; `backend/tests/test_financial_*.py` **50 files**,
**3,164 tests**.

### Gate baselines as of `4324b24`

- **Backend financial suite: `Ran 3164 tests, OK (skipped=12)`.** Unchanged; no
  backend file was touched this session. The gate was run in full anyway and the
  count line was read, not inferred from the exit code. **There are no expected
  failures.**
- **Frontend unit: 62 files, 405 tests, all passing.** Up from 60 / 395. The
  delta is exactly the two files added this session and their ten tests:
  `FinancialPage.test.tsx` (6) and `financial.store.test.ts` (4). Nothing else
  moved. The `CLAUDE.md` figure of 54/285 is stale; 405 includes the stray probe
  test.
- **Frontend browser: 2 files, 4 tests — NOT RUN THIS SESSION.** See the disk
  note under Durable facts. The number above is carried from `17d94ac` and has
  not been re-verified. It cannot cover this change either way: its only two
  files are `TextSearchPanel.browser.test.tsx` (evidence) and
  `CaseSettingsPage.browser.test.tsx` (cases), and grepping both for financial
  and ledger imports returns nothing, while every file changed this session is
  under `features/financial/`. **Re-run it next session if the disk allows.**
- **`tsc -b --force` returns 0. `eslint .` returns 0.** Both re-run after the
  last edit.

---

## What this session did

**Phase 1 item 4 of the wiring plan: mount the ledger screen.** Committed as
`4324b24`, four files, 533 insertions, 142 deletions. All frontend. **This
closes Phase 1.**

`LedgerPanel` was built two sessions ago and mounted nowhere. It is now the tab
the financial page opens on. Rows that could be created from seven places in the
interface can now be seen.

### Two rulings taken this session, both from Neil

- **Four peer tabs.** The strip reads Ledger, Transactions, Counterparties,
  Trends. The graph views do **not** collapse behind a single entry. This closes
  the open question "Do the three graph tabs stay three peers of the ledger tab?"
  which the previous session raised and could not answer.
- **Always open on the Ledger.** The financial page's tab choice is no longer
  saved to the browser at all. Every visit opens on the Ledger regardless of
  where the reader was last time. This was chosen over migrating the stored
  value.

### What landed

Two files modified, two created.

- **`stores/financial.store.ts`** (+38/−3). `"ledger"` added to the view union
  with a docstring saying plainly that this is **the tab on the financial page
  and nothing wider** — the name `mainView` reads like it could mean the app's
  main view and does not. Default flipped to `"ledger"`. `mainView` removed from
  `partialize`, and an explicit `merge` added.
- **`components/FinancialPage.tsx`** (+219/−139). The restructure, described
  below. Most of the deletions are the two early returns and the chrome block
  moving rather than being removed, so the line count overstates the change.
- **`stores/financial.store.test.ts`** (77 lines, 4 tests). New.
- **`components/FinancialPage.test.tsx`** (199 lines, 6 tests). New — **the page
  had no test at all before this session.**

### The restructure, and what it fixes

The page held two early returns **above the tab strip**, both keyed on the Neo4j
graph query: one while it was in flight, one when it came back with no rows.

A case whose bank file has just been sent to the relational ledger is exactly
that shape — ledger rows, no graph. Under the old arrangement it rendered a
full-page "No documentary transactions" and **no tabs at all**, so the rows that
did exist were unreachable. Both returns now sit inside the three graph tabs, in
a `graphTab(content)` helper, so the graph reports its own emptiness in its own
tab and the Ledger tab is always reachable. Four of the six page tests exist to
stop that early return coming back.

The four pieces of graph chrome moved inside the graph tabs with them, collected
in a `graphChrome` fragment: `FinancialToolbar`, the `uses_legacy_financial_model`
banner, `FinancialFilterPanel` and `FinancialSummaryCards`. Their counts, filters
and totals are computed from graph rows; drawn above a ledger table they would
read as a description of it. **They did not become tab-aware** — moving them
leaves four components each describing one store, and no component that has to be
right about which store is on screen.

### Why stopping persistence took two mechanisms, not one

This is the part that would have been silently half-done.

Dropping `mainView` from `partialize` stops a tab choice being **written**. It
does not stop one already written being **read**. Any browser that used this page
before today still holds `"transactions"` in `owl-financial-store`, and zustand's
default merge lays the stored object over the initial state on rehydrate. Without
the second half, every existing user would keep landing on the graph and the
change would be visible only to people who had never opened the page.

So there is an explicit `merge` that deletes `mainView` from the persisted object
and keeps everything else — page size, sort columns, mode. **A discard rather
than a `version`/`migrate` bump**, because a discard is version-independent and
cannot be defeated by a blob an older build writes later. The store test asserts
both halves separately: what gets written, and what survives being read back.

### A correction to the wiring plan, lines 121–123

The plan says adding a tab value "needs a migration or it will read a stale
persisted value it does not recognise." **That is wrong in this direction.** Once
`"ledger"` is added to the union, a stored `"transactions"` is still a valid
member — nothing fails to recognise it. The only consequence was landing on the
wrong tab. The plan's other line, "a sibling route is the current
recommendation", was overruled two sessions ago. Both are now superseded by the
work; leaving the text in place is fine as history, but do not act on it.

### Verification

Both gates as recorded above. The frontend unit delta of exactly 2 files and 10
tests confirms nothing else moved.

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

- **The sandbox disk can be full, and `playwright install` is where you find
  out.** `npx playwright install chromium` failed with `ENOSPC: no space left on
  device`; `df -h` showed 9.6G total, 9.4G used, **99% full, 177M free**. The
  space is in `/tmp` caches left by **earlier sessions under different uids**
  (`mutate_exports_cache` 61M, `pyc_run` 43M, `pyc_all` 42M and others), and the
  sticky bit means a session cannot remove them.
  `find /tmp -maxdepth 1 -user $(id -un)` showed my own files totalling well
  under 100K — **there is nothing a session can reclaim.** If the browser gate is
  needed and chromium is not already installed, either Neil clears `/tmp` or the
  gate is honestly recorded as not run. **Do not claim it green.**
- **Radix tab triggers activate on `mousedown`, not `click`.** Verified by
  reading `node_modules/@radix-ui/react-tabs/dist/index.mjs`: `activationMode`
  defaults to `"automatic"` (line 30), the trigger carries `onMouseDown`
  (line 121) and `onFocus` (line 131), and **there is no `onClick`**.
  `fireEvent.click` therefore leaves the tab where it was, and **every assertion
  after it silently describes the previous tab** — the test still passes, it just
  tests the wrong panel. Use `fireEvent.mouseDown`. The `selectTab` helper in
  `FinancialPage.test.tsx` carries this reasoning.
- **`TooltipProvider` is mounted app-wide at `app/providers.tsx:13`,** so any
  page test that renders a component using a tooltip needs one too.
  `TransactionTable` does. Without it the table throws
  ``Tooltip` must be used within `TooltipProvider`` into its own `ErrorBoundary`,
  which **catches it, so the test passes** while the tab it asserts is showing
  the graph is in fact showing a caught error. It surfaces only as stderr noise.
  `RouteBadge.test.tsx:43` and `GraphToolbar.test.tsx:9` already wrapped for
  this reason.
- **Vitest does not typecheck.** All ten new tests passed while
  `makeGraphRow()` was missing two required fields of `Transaction`; only
  `tsc -b --force` caught it. **Run `tsc` after writing test fixtures, not just
  after writing product code**, and use `--force` when it matters, since `-b` is
  incremental.
- **A `Transaction` fixture needs six fields minimum.** `BaseFinancialRecord`
  (`financial/api.ts:3–86`) requires `key`, `amount`, `from_entity`, `to_entity`,
  `financial_record_kind`, `financial_view_mode` and `is_financial_event`;
  `TransactionRecord` adds `is_evidence_backed_transaction`.
- **`use-filtered-transactions.ts` is pure `useMemo` with no react-query,** so a
  page test can leave it real and mock only `use-financial-data` and
  `use-ledger-transactions`. Mocking the two hook modules is enough to control
  the whole page.
- **`FinancialToolbar`'s placeholder `"Search transactions..."` is a reliable
  probe for whether the graph chrome is on screen.** Used in three of the page
  tests.

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
- **The ledger cannot silently double, and it is the schema that guarantees it.**
  `ref_id` is deterministic from `(file sha256, row content)` and
  `uq_financial_transactions_case_ref` is on `(case_id, ref_id)`. Any future
  reasoning about duplicate ingestion starts here. **Do not restate the old claim
  that a second run doubles the money; it is wrong.**
- **A failure inside a `with ingestion_run(...)` block must roll back the
  caller's session before it leaves.** Otherwise the open write transaction
  contends with the run's own bookkeeping session, `_terminate_quietly` swallows
  it by design, and the run is left `running`.
- **`IntegrityError` text is not portable.** SQLite names the offending
  **columns**, Postgres names the **constraint**. Assert the table name.
- **`financial_source_documents` is unique on
  `(ingestion_run_id, evidence_file_id)`** — one row per file per run.
- **`evidence_files.stored_path` is `NOT NULL`.** The pathless file that
  production can actually hold is the **empty string**, not `None`.
- **DB-backed financial tests need file-on-disk SQLite, not `:memory:`.**
- **Prefer `ingestion_run` (the context manager) over `open_ingestion_run`.**
- **NACHA yields accounts and no periods.** It is not a statement. Verified
  across all four formats: camt 3/3 rows and a period, BAI2 3/3 and a period,
  MT940 2/2 and a period, NACHA 1/1 and **no** period. Junk bytes give
  `unrecognised`.
- **The century window is required and never defaulted.** Max span
  `CENTURY_WINDOW_MAX_SPAN_YEARS = 99`; wider, or backwards, is a 400.
- **A precheck verdict is not a promise the write will succeed.**
  `contradictory_period` and `already_ingested` are decided against rows already
  stored, not against the file. `would_ingest` is shorthand for one value of
  `outcome`, nothing more.
- **`wouldStore` and `didStore` read the endpoint's flag, never the outcome
  word.** A backend one version ahead sends a word this build has never seen, and
  recomputing storability from the word would hide the store button on a file the
  backend is willing to take.
- **An unrecognised vocabulary member is named, never rendered blank,** because
  an empty badge reads as an answer. **No outcome maps to the `default` badge
  variant and the tests forbid it** — `Badge` falls through to `default` for an
  unmapped key, and `default` is a loud filled primary, so a forgotten member
  would arrive looking like the most important thing on screen.
- **A held file is not necessarily a ledger file.** `blocksDocumentProcessing`
  covers four outcomes; `belongsToLedger` covers one. Any future action attached
  to a held row has to pick deliberately between them.
- **A compound `cmd; echo "exit: $?"` inside a longer `&&` chain can report an
  empty exit code**, and `$?` after a pipe is the pipe's status, not the
  command's. Redirect to a per-user file and check separately.
- **The exports guard is automatic.** `tests/test_financial_exports.py` globs
  `*.py` in the package and asserts each module contributes at least one name to
  `__all__`. A new module needs **no manual list entry**, contrary to the note in
  `CLAUDE.md`.
- **Every Bash command needs its own absolute `cd`.** Where a `cd` is awkward,
  `PYTHONPATH=<abs>/backend` works for one-liners. This was nearly missed twice
  this session; the working directory happened to be right, which is luck.
- **Any scratch file in `/tmp` needs a per-user name,** including the git index.
- **`GIT_INDEX_FILE` does not survive between Bash invocations.** Staging and
  `git write-tree` must happen in one command. `commit-tree` can be a second
  command **provided it passes the tree hash you already verified** — done again
  this session, worked again.
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
  child's `data-slot`**, so a badge inside a tooltip is found by `data-variant`
  instead (`RouteBadge.test.tsx`).
- **`Badge` spreads `React.ComponentProps<"span">`.** Variants are `default`,
  `secondary`, `destructive`, `outline`, `success`, `danger`, `warning`, `info`,
  `amber`, `slate`.
- **`tsconfig` has `strict: true` but not `noUncheckedIndexedAccess`.**
- **React Query is `^5.90.21`**, so `isPending`, not `isLoading`.
- **Any new code touching `amount_minor` must use `formatLedgerAmount`,** whose
  `currency` parameter is a **required `string`** — a caller holding
  `string | null` must decide what an absent currency means rather than pass it
  through.
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

### The ledger screen's own rules, now that it is mounted

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
- **Phase 2, make the rows trustworthy** — runs, quarantine, reconciliation,
  adjudication and proof class, duplicates, suspect amounts, locators.
- **Phase 3, make the ledger the source of the graph** — projection, continuity
  and coverage, linkage and correlation and flow.
- **Phase 4, get it out** — exhibit and export, tracing.

**Next unit: Phase 2 item 5, ingestion runs.** `RunCounts`, run status,
`reap_stale_runs`. What happened during an ingest, and what a run that died left
half-done. The plan puts it first in this phase because it is the record of the
thing Phase 1 just finished building, and **a failed ingest is otherwise
invisible** — the send dialog reports what one call did and nothing anywhere
reports a run that never completed. The plan's reading list for it:
`runs.py`, plus whatever the frontend needs to show a run.

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
exposing source document type onto the transaction row. **Note that this now
interacts with a decision taken today:** the financial page no longer persists
which tab you were on, so if user-defined tabs are ever built, the question of
what is remembered across visits has to be reopened deliberately rather than
inherited.

14 money movement over time, 15 follow the money: both still parked, both still
new capability rather than wiring. 16 tracing and 17 exhibit tagging are **no
longer parked** — they are Phase 4 of the plan.

---

## Open questions, waiting on Neil

**Where does the ledger screen mount?** **Answered and now built.** A tab inside
`FinancialPage`, the primary view of it, four peer tabs with Ledger first.

**Does the graph chrome move or become tab-aware?** **Answered and now built: it
moved inside the graph tabs.**

**Do the three graph tabs stay three peers of the ledger tab?** **Answered this
session: yes, four peer tabs.**

**Was removing `reingest` the right call?** Raised two sessions ago, still
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

**Should the engagement period live on the case?** Raised as an alternative to
two date fields per dialog. **Answered by construction for now, not by ruling:**
the dialog asks for the window every time, because the alternative is new schema.
If a case ever grows a date range, the dialog should default from it rather than
stop asking, since a file can legitimately fall outside the engagement period and
the reader has to be able to say so.

**Provenance of `exhibit.py`.** Unchanged: confirmed valuable, but it came from a
proposed build order, not a stated Owl requirement.

---

## Standing flags

- **Phase 1 is closed: a bank file can be sent to the ledger from seven places
  and the rows it creates are now visible.** The gap flagged here for the last
  two sessions is gone.
- **The Neo4j financial view is not a projection of the ledger.** `projection.py`
  has zero production callers. Whatever writes those graph nodes today writes them
  independently, so the two stores can disagree and nothing detects it. Phase 3
  item 12 closes this. **Do not describe the graph as derived from the ledger
  until it is.** The financial page now shows both stores side by side in one tab
  strip, which makes a disagreement visible to a reader for the first time, and
  nothing in the interface explains it. Worth a ruling on whether the page should
  say anything about that before Phase 3 lands.
- **A failed or half-finished ingestion run is invisible everywhere.** This is
  what Phase 2 item 5 exists to fix and it is the reason that item is next.
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
- **The sandbox disk is at 99%.** See Durable facts. It cost the browser gate this
  session and it will cost the next session too unless `/tmp` is cleared from
  outside.

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
- **`docs/loupe-wiring-plan.md` lines 117–123 are now superseded** by the work and
  by two rulings. Left in place as history; do not act on them.
