# Loupe build state

Where the work stands. Rewritten whenever a unit lands. Durable rules live in
`CLAUDE.md` at the repo root, not here.

**Last updated:** 5 September 2026 (records the send-to-ledger interface, `17d94ac`)

---

## Position

- **Branch:** `integration/evidence-main-reunion`
- **Head when this was written:** `17d94ac`
  (`17d94ac12f83cf470594768e544d089abb8db3e4`), "The interface sends a held bank
  file to the ledger", parent `a0b9efe`. **Confirm the real tip with
  `git log --oneline -5`** at the start of every session rather than trusting
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
  investigation six sessions ago. It is **counted in the frontend baseline
  below** (it contributes 1 file and 1 test), so when it is deleted the unit
  numbers drop by one each and that is expected, not a regression.

Also untracked, and **not** mine — Neil's own documents, left alone:
`docs/IP_Protection_Strategy.docx`, `docs/ip-protection-strategy.md`,
`docs/owl-project-brief.md`.

### Scale

85 commits since `c4246c0` (27 August), counting `17d94ac`.

Backend unchanged this session: `backend/services/financial/` **46 modules**,
**33,759 lines**; `backend/tests/test_financial_*.py` **50 files**,
**3,164 tests**.

### Gate baselines as of `17d94ac`

- **Backend financial suite: `Ran 3164 tests, OK (skipped=12)`.** Unchanged; no
  backend file was touched this session. The gate was run in full anyway.
  **There are no expected failures.**
- **Frontend unit: 60 files, 395 tests, all passing.** Up from 58 / 354. The
  delta is exactly 2 files and 41 tests: `ingest-format.test.ts` (19, new),
  `SendToLedgerDialog.test.tsx` (13, new), and `ProcessHoldDialog.test.tsx`
  (21 → 30). The `CLAUDE.md` figure of 54/285 is stale; 395 includes the stray
  probe test.
- **Frontend browser: 2 files, 4 tests.** `tsc -b` returns 0. `eslint .` returns 0.

---

## What this session did

**Phase 1 item 3 of the wiring plan: the interface sends it.** Committed as
`17d94ac`, ten files, 1,881 insertions, 5 deletions. All frontend.

The two endpoints existed and nothing called them. They are now reachable from
the interface, which closes Phase 1's ingestion half. **A bank file held by the
gate is no longer a dead end.**

### What landed

Five new files under `frontend_v2/src/features/financial/`:

- **`lib/ingest-format.ts`** (255 lines). The vocabulary layer: copy and badge
  variants for all seven precheck outcomes and all twelve ingest outcomes, plus
  `wouldStore`, `didStore`, `formatPeriodRange`, `accountLabel`.
- **`lib/ingest-format.test.ts`** (232 lines, 19 tests).
- **`hooks/use-ledger-ingest.ts`** (70 lines). `usePrecheckFile` and
  `useIngestFile`, two mutations. The ingest one invalidates
  `["financial-ledger", caseId]` **only when `result.stored`** — an
  `already_ingested` answer changed nothing and refetching on it would be a
  request sent to say so.
- **`components/SendToLedgerDialog.tsx`** (424 lines). The three-step dialog.
- **`components/SendToLedgerDialog.test.tsx`** (419 lines, 13 tests).

Five modified:

- **`financial/api.ts`** (+224). The wire types and the two calls.
- **`financial/lib/ledger-format.ts`** (+19/−5). `narrow` and `TermCopy`
  exported, with a new optional `source` argument defaulting to `"the ledger"`
  so existing behaviour is unchanged byte for byte. Precheck passes
  `"the reading"`.
- **`evidence/hooks/use-guarded-process.ts`** (+8). `caseId` on the returned
  gate.
- **`evidence/components/ProcessHoldDialog.tsx`** (+44/−0) and its test
  (+191).

### The shape of the dialog, and why it has three steps

Ask, read, store. The middle step writes nothing.

**Step one asks for the period,** because it has to. `window_start` and
`window_end` are required query parameters on both endpoints and cannot be
defaulted or derived — three of the four native formats print two-digit years
and nothing carries the century. The read button stays disabled until both are
given. `default_currency` is offered beside them, optional, trimmed, and sent as
`undefined` when blank.

**Step two shows what the file says it holds** — the outcome, the accounts, the
row counts, the span the statement actually covers, the opening and closing
balances — with a "Change dates" button beside it, because the most likely
reason a reading looks wrong is that the window was wrong.

**Step three is offered only when the endpoint says it would take the file.**
The store button is gated on `would_ingest`, the endpoint's own flag, never on
the outcome word.

### Decisions taken, and the reasoning for each

**`wouldStore` and `didStore` read the flag rather than judge the word.** They
are one line each and are tested anyway, because the failure they prevent is
silent: a backend one version ahead sends an outcome word this build has never
seen, and any code that recomputed storability from the word would hide the
store button on a file the backend is willing to take. The test pins the
combination that catches it — an unknown word with `would_ingest: true`.

**An unrecognised outcome is named in the label, not rendered blank.** A word
from a future backend is not an error and must not come through as an empty
badge, because an empty badge reads as an answer. It says
`Unrecognised (<word>)` and explains that the screen is older than the service.
Precheck attributes it to "the reading" and ingest to "the ledger", because no
row was written on the precheck path and pointing at the ledger would send
someone to look for one.

**No outcome is mapped to the `default` badge variant, and the tests forbid it.**
`Badge` falls through to `default` for a key a variant map does not carry, and
`default` is a loud filled primary — so an outcome nobody wrote copy for would
arrive on screen looking like the most important thing on it. A member mapped to
`default` deliberately would be indistinguishable from one that was forgotten,
so `default` is banned outright and unrecognised words get `outline`.

**`already_ingested` is not coloured or worded as a failure.** Nothing was
stored and that is the correct answer. It does not claim rows were added.

**The action on the held rows is offered for `native` only.** `belongsToLedger`
is deliberately narrower than `blocksDocumentProcessing`: four outcomes block the
document pipeline, but the reading requires exactly one format to claim the
bytes, so an `ambiguous` file would be refused at the ledger too. **A button that
can only be refused is worse than no button.** Tested in both directions, since
the two plausible mistakes are opposite ones.

**`useGuardedProcess` returns `caseId` rather than the dialog taking a new
prop.** Seven render sites get it free that way. A prop would have been seven
chances to forget it, and the failure would have been a send dialog pointed at no
case.

**The send dialog is a sibling of the hold dialog, not a child.** It is not
unmounted by the hold closing underneath it, neither one's escape handling has to
know about the other, and the hold stays open behind it — sending one bank file
says nothing about the rest of the request, and the cleared files are still
undecided. One send dialog at a time, held in the parent rather than per row,
because the dialog asks for a period and two of them open at once would invite
the reader to answer that twice with no sign the answers differed.

### Verification

Both gates green and recorded above. The frontend unit delta of 41 is exactly
19 + 13 + 9, which confirms nothing else moved.

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

- **Chromium is not installed in a fresh sandbox and the browser project fails
  loudly when it is missing** — `browserType.launch: Executable doesn't exist`,
  reported as an unhandled error with "no tests", not as a test failure.
  `npx playwright install chromium` takes about 30 seconds and 106 MiB. **Do not
  pass `--with-deps`**; it needs root. Budget for this once per session if the
  browser gate is in scope.
- **`vi.mock` factories are hoisted above `const` declarations, so a mock that
  has to capture a prop needs `vi.hoisted`.** Used in
  `ProcessHoldDialog.test.tsx` to keep the send dialog's `onClose` reachable:
  the stub renders nothing clickable, so the close is exercised by calling the
  captured prop inside `act`.
- **Mock the seam, not the network, when a component owns real hooks.**
  `use-ledger-ingest.ts` reaches the client by property access at call time
  (`financialAPI.precheckFile(...)`), so `vi.spyOn(financialAPI, "precheckFile")`
  works and lets `SendToLedgerDialog.test.tsx` drive the real mutations against a
  real `QueryClient`. Set `mutations: { retry: false }` as well as `queries`, or
  a rejection is retried and the assertion races it.
- **Walk the vocabulary array in the test rather than re-typing the list.** The
  compiler catches a gap in a `Record<Outcome, ...>` only for members this build
  knows about; a member added to `api.ts` and forgotten everywhere else is caught
  only by iterating `INGEST_OUTCOMES` itself. A companion assertion on the array
  lengths (7 and 12) catches the reverse — a copy table gaining a member the
  array never got.
- **A held file is not necessarily a ledger file.** `blocksDocumentProcessing`
  covers four outcomes; `belongsToLedger` covers one. Any future action attached
  to a held row has to pick deliberately between them.

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
- **A compound `cmd; echo "exit: $?"` inside a longer `&&` chain can report an
  empty exit code.** Redirect to a per-user file and check separately.
- **The exports guard is automatic.** `tests/test_financial_exports.py` globs
  `*.py` in the package and asserts each module contributes at least one name to
  `__all__`. A new module needs **no manual list entry**, contrary to the note in
  `CLAUDE.md`.
- **Every Bash command needs its own absolute `cd`.** Where a `cd` is awkward,
  `PYTHONPATH=<abs>/backend` works for one-liners.
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
  `@testing-library/react`, `data-testid` for anything a test needs to find, and
  `fireEvent` never `userEvent`.
- **Radix `DialogContent` renders a corner X carrying an `sr-only` "Close",** so
  a footer button named "Close" makes `getByRole` ambiguous. Tell them apart by
  `data-slot="dialog-close"`, which radix sets and we do not. `footerButton()` in
  `ProcessHoldDialog.test.tsx` is the helper.
- **`Badge` spreads `React.ComponentProps<"span">`.** Variants are `default`,
  `secondary`, `destructive`, `outline`, `success`, `danger`, `warning`, `info`,
  `amber`, `slate`. An unmapped lookup falls through to `default`, a **loud filled
  primary**, so a variant map must be explicit for every member.
- **`tsconfig` has `strict: true` but not `noUncheckedIndexedAccess`.**
- **React Query is `^5.90.21`**, so `isPending`, not `isLoading`.
- **Any new code touching `amount_minor` must use `formatLedgerAmount`,** whose
  `currency` parameter is a **required `string`** — a caller holding
  `string | null` must decide what an absent currency means rather than pass it
  through. In `SendToLedgerDialog` the balance line is dropped entirely, because
  an amount with no currency beside it is not a number anyone can read.
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

- **Phase 1, make rows exist** — precheck endpoint ✅ `a4eb3dc`, ingest endpoint
  ✅ `43f8358`, the interface action on a held file ✅ `17d94ac`, mount the
  ledger.
- **Phase 2, make the rows trustworthy** — runs, quarantine, reconciliation,
  adjudication and proof class, duplicates, suspect amounts, locators.
- **Phase 3, make the ledger the source of the graph** — projection, continuity
  and coverage, linkage and correlation and flow.
- **Phase 4, get it out** — exhibit and export, tracing.

**Next unit: Phase 1 item 4, mount the ledger screen.** It is now the only thing
between a user and the rows they can already create, and that gap is new as of
this session: **a bank file can be sent to the ledger from seven places in the
interface, and there is no screen anywhere that shows what arrived.** Rows go in
and vanish from view.

**Neil has ruled: the ledger is a tab inside `FinancialPage`, and it is the
primary view of that page.** The sibling route is dead. Do not reopen it, and do
not add a ninth sidebar entry. The naming problem it carried — two
financial-looking entries in a sidebar that could not say which store each read
— is gone with it.

The ruling settles where, not how. Three things in the page block it, all
verified against source on the day of the ruling:

- **The page early-returns before the tabs exist.** Line 323 is
  `if (!transactions.length)`, over the **Neo4j** read, with a loading return at
  315 above it. So the tab strip renders only when the graph has rows, and a
  nested ledger tab is unreachable exactly when a freshly ingested case has
  ledger rows and no graph. That case is no longer hypothetical: it is what the
  send-to-ledger work made producible from seven places in the interface.
  `LedgerPanel` already owns its own no-case, loading, error and empty states,
  so **the guard moves inside the graph tabs rather than wrapping the page.**
- **Four pieces of chrome sit above the tab strip and describe the graph.**
  `FinancialToolbar` (`filteredCount`, `totalCount`), the
  `uses_legacy_financial_model` banner, `FinancialFilterPanel` (graph categories
  and entities) and `FinancialSummaryCards` (totals over `filteredTransactions`).
  With the ledger primary, the first thing on screen is a row of counts and
  totals that do not describe the table beneath them — the exact failure the
  standing rule about corrected values exists to prevent. That chrome must move
  inside the graph tabs or become tab-aware. **Which of those two is still
  Neil's call and has not been made.**
- **`mainView` is persisted and has no migration.** `financial.store.ts` writes
  it to `owl-financial-store` through `partialize`; the file contains zero
  occurrences of `version` or `migrate`. Changing the default to the ledger
  therefore moves new users only — anyone who has opened the page before
  rehydrates a stored `"transactions"` and lands where they always did. Needs a
  `version`/`migrate` pair or an explicit rehydration rule, or the ruling is
  silently half-applied.

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
items 1 to 3, **all three of which are now done**.

13, user-defined view tabs, is **not in the wiring plan** — new capability rather
than connecting built capability, so it stays parked until the plan is worked
through. Two things, not one: named persisted snapshots of filter state, and
exposing source document type onto the transaction row.

14 money movement over time, 15 follow the money: both still parked, both still
new capability rather than wiring. 16 tracing and 17 exhibit tagging are **no
longer parked** — they are Phase 4 of the plan.

---

## Open questions, waiting on Neil

**Where does the ledger screen mount?** **Answered.** A tab inside
`FinancialPage`, and the primary view of it. No sibling route, no ninth sidebar
entry. Detail and the three things that block it under Build order above.

**Does the graph chrome move or become tab-aware?** **Raised by the mount ruling
and not yet answered.** The toolbar, legacy banner, filter panel and summary
cards all render above the tab strip and all read Neo4j. With the ledger primary
they would head the screen with counts and totals belonging to the other store.
Either they move inside the graph tabs, or they learn which tab is showing.
Moving them is the smaller change and the more honest one; making them
tab-aware keeps the page's shape but leaves four components that have to be
right about a thing they currently never ask. **Item 4 can start without this
answer only if the ledger tab is built first and the chrome is left untouched
until the ruling lands.**

**Was removing `reingest` the right call?** Raised last session, still unruled.
Short form: the override could not succeed for unchanged bytes, and where it
could succeed it would leave two contradictory readings of one file in one case
with nothing able to resolve them until `duplicates.py` is wired at Phase 2 item
9. **Reversible — say the word and it comes back.** Note that the send dialog
built this session has no override either, for the same reason: it reports
`already_ingested` plainly and offers nothing to force past it.

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

- **Rows can now be created from the interface and cannot be seen anywhere.**
  Seven components render `ProcessHoldDialog`, every one of them now offers a
  held bank file a route to the ledger, and `LedgerPanel` is still mounted
  nowhere. `GET /api/financial/ledger` will start returning rows on real cases as
  soon as anyone uses it. **This is the strongest argument for Phase 1 item 4 and
  it did not exist before this session.**
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
