# Loupe build state

Where the work stands. Rewritten whenever a unit lands. Durable rules live in
`CLAUDE.md` at the repo root, not here.

**Last updated:** 5 September 2026 (records the ledger screen, `94af112`)

---

## Position

- **Branch:** `integration/evidence-main-reunion`
- **Head when this was written:** `94af112`
  (`94af112e0ddd438fe971659c29ce5008454d01da`), "The ledger screen: relational
  ledger rows as a table a reader can trust", parent `0581b3a`. **Confirm the
  real tip with `git log --oneline -5`** at the start of every session rather
  than trusting this line.
- **Nothing is pushed.** Push is blocked; Neil pushes.

### Uncommitted

Nothing tracked. The tree is clean.

Still untracked and still un-removable from a session (workspace denies
`unlink`) — Neil has to delete these from his side:

- `backend/services/financial/export_manifest.py.bak`
- `backend/services/financial_export_service.py.bak`
- `frontend_v2/src/__probe.test.ts` — a diagnostic left by the vitest
  investigation three sessions ago. It is **counted in the frontend baseline
  below** (it contributes 1 file and 1 test), so when it is deleted the unit
  numbers drop by one each and that is expected, not a regression.

### Scale

77 commits since `c4246c0` (27 August), counting `94af112`.

Backend unchanged for two sessions; these figures were measured then:
`backend/services/financial/` **44 modules**, **32,452 lines**;
`backend/tests/test_financial_*.py` **47 files**, **3,057 tests**.

---

## What this session did

One build item: **the ledger screen**, item 12's second remainder. Committed as
`94af112`, 981 insertions across four files, no deletions.

The previous session built the data layer — the fetch, the money scaling, the
vocabulary narrowing. This session builds the thing that puts it on a screen. It
splits in two on purpose, so the drawing half can be tested against rows alone
rather than staged through a query.

### What landed

- `frontend_v2/src/features/financial/components/LedgerTable.tsx` — **new, 367
  lines.** Presentational. Takes `LedgerTransaction[]` and draws them. Knows
  nothing about fetching.
- `frontend_v2/src/features/financial/components/LedgerPanel.tsx` — **new, 125
  lines.** The fetching half. Owns the four states a table cannot be in the
  middle of: no case chosen, in flight, failed, returned empty.
- `frontend_v2/src/features/financial/components/LedgerTable.test.tsx` — **new,
  298 lines, 21 tests.**
- `frontend_v2/src/features/financial/components/LedgerPanel.test.tsx` — **new,
  191 lines, 10 tests.** Mocks the hook rather than the network, because what is
  under test is the panel's reading of a query result, not the query.

### Two facts read out of the backend, not assumed

Both changed what got built. Recorded here because a later session looking at
the panel will otherwise wonder why it is doing more than rendering.

**1. The ledger read defaults to `admitted`.** `list_transactions` in
`backend/services/financial/transaction_query.py` does
`status = ledger_status if ledger_status is not None else LedgerStatus.admitted`
— it substitutes a filter, rather than returning every row regardless of status.
So zero rows does **not** mean the case has no financial material. It means
nothing holds that one status, and the quarantined, superseded and rejected rows
are sitting outside the filter, uncounted and unshown. An empty state reading "no
transactions" would state the opposite of what was checked. The one that shipped
names the status it filtered on and says where the rest are.

**2. `total` is `len(transactions)` of the same response.** Verified in
`backend/routers/financial_ledger.py`; there is no paging behind it. Reading a
count from `total` would be reading a number that means "how many are in front of
you" while implying "how many exist". So the count comes from `rows.length`, the
two are compared, and a disagreement is surfaced — because the only way they can
differ is a backend that has started paging without this screen knowing, at which
point every figure derived from a page is a figure over a subset.

Also read rather than assumed: `list_transactions` orders by
`ordering_date.asc(), row_index.asc()`. The second of those is what keeps a
statement's own printed sequence intact where one day holds several movements. So
the table draws rows in the order they arrive and does not sort. **Do not add
client-side sorting without dealing with that.**

### The three things in the table that are correctness, not presentation

Each exists because the alternative misleads silently rather than loudly.

**An unscaled amount is marked.** `formatLedgerAmount` returns `scaled: false`
when it could not turn a stored minor-unit count into a figure, and its own
docstring is explicit that a caller which renders that without saying so shows
123456 where 1,234.56 belongs. The marker is not decoration; dropping it turns a
hundredfold error into a plausible number.

**An absent running balance is stated in words.** `running_balance_minor` is
nullable, and a blank cell reads as zero, or as a balance of nothing, neither of
which is what null means. See the standing flag below: on the current corpus this
is **every row**.

**An unrecognised vocabulary member is shown, loudly.** Every closed vocabulary
arrives as a bare string or int and is narrowed at runtime, so a backend one
version ahead of this build can send a member this build has never heard of. Those
rows still render, still show the raw value, and carry a reserved `warning` badge
plus `data-unrecognised="true"` — because a blank badge on a financial row reads
as an answer. The attribute exists so tests assert on the narrowing rather than on
a class name.

### Verification, all run this session

- Frontend unit project: **58 files, 354 tests, pass** (was 56 / 323; +2 files
  and +31 tests, exactly the new work).
- Frontend browser project: **2 files, 4 tests, pass**.
- `npx tsc -b`: 0. `npx eslint .`: 0.
- Commit verified by `git diff --stat HEAD <tree>` before the ref was written:
  exactly the four intended files, 981 insertions, no deletions. Tree
  tracked-clean afterwards.

Backend was not re-run; nothing backend changed.

**Mutation-tested in four rounds**, because a test that has never been seen to
fail is not evidence of anything. Each round rewrote exactly one expression, with
`assert s.count(old) == 1` so a missed match failed loudly rather than silently
mutating nothing:

- `data-unrecognised={unrecognised ? "true" : "false"}` pinned to `"false"` →
  **2 failed / 19 passed**, exactly the two `TermBadge` tests. The date-source and
  extraction-layer badges carry their own inline flags, so their tests correctly
  still passed.
- `{!amount.scaled && (` → `{false && (` → **1 failed / 20 passed**.
- The string `No running balance` emptied → **1 failed / 20 passed**.
- `{countDisagrees && (` → `{false && (` in the panel → **1 failed / 9 passed**.

Both files were restored from per-user backups, `diff` confirmed byte-identical,
and the suite re-run green at 31.

---

## Durable facts, kept so no one rediscovers them

The bootstrap, the baselines, the `VITE_CACHE_DIR` requirement, the playwright
install, the storybook limitation and the git procedure all live in
**`CLAUDE.md`**. Deliberately not duplicated here.

### New this session

- **`GIT_INDEX_FILE` does not survive between Bash invocations.** The staging and
  the `commit-tree` have to happen in **one** command. Splitting them means the
  second call writes against the real index. The tree hash is the check: stage
  again, confirm `git write-tree` reproduces the hash you verified, then commit in
  the same breath.
- **`&&`-chaining a `grep` that finds nothing silently kills the rest of the
  line.** `grep` exits 1 on no match, so `git status | grep -v '^??' && echo ...`
  prints nothing and looks like the command ran. Use `;` between verification
  steps, never `&&`.
- **The house component-test conventions** are `render`/`screen` from
  `@testing-library/react`, `data-testid` for anything a test needs to find, and
  `fireEvent` never `userEvent`. The cleanest exemplar is
  `src/features/financial/components/TransactionSourceHighlight.test.tsx`.
- **`Badge` spreads `React.ComponentProps<"span">`**, so `title` and `data-*` pass
  through. Its variants are `default`, `secondary`, `destructive`, `outline`,
  `success`, `danger`, `warning`, `info`, `amber`, `slate`. An unmapped lookup
  falls through to `default`, which is a **loud filled primary** — so a variant map
  must be explicit for every member rather than left empty.
- **`tsconfig` has `strict: true` but not `noUncheckedIndexedAccess`**, so
  indexing a `Record<string, T>` types as `T` and not `T | undefined`.
- **React Query is `^5.90.21`**, so `isPending` is the settled name, not
  `isLoading`.
- **Verify a `lucide-react` export before importing it.** `node -e` against the
  package is a two-second check and it is cheaper than a compile failure. The
  icons used here — `CircleAlert`, `CircleHelp`, `TriangleAlert`, `Loader2`,
  `ScrollText` — are all present.

### Carried forward, still true

- **Any scratch file in `/tmp` needs a per-user name.** `/tmp` is sticky and the
  sandbox user changes every session; a plain `/tmp/tsc.out` from an earlier
  session is owned by another uid and a redirect into it fails with
  `Permission denied`, which looks exactly like the command having failed. Use
  `/tmp/<name>-$(id -un).<ext>` for everything.
- **No shared money formatter existed before the data-layer unit.** Other
  financial components reach for `toLocaleString("en-US", ...)` on a float. Those
  are the Neo4j-backed `Transaction` rows, which carry floats, so they are not
  wrong today — but any new code touching `amount_minor` must use
  `formatLedgerAmount` and nothing else.
- **SQLAlchemy flush ordering does not follow raw ForeignKeys.** With no ORM
  `relationship()` between two mappers, commit the parent row first, then the
  dependent row in a second commit.
- **The full engine pytest suite cannot run on 3.10** — pre-existing
  `from datetime import UTC` in
  `evidence-engine/app/services/pipeline_run_state.py` is 3.11+ only.
- **The exports guard needs no edit for a new module**, as long as the module
  contributes names through `__init__.py` and has no module-level `__all__`.
- **The storybook vitest project cannot run here** and no story covers financial
  code. "vitest is green" only ever means the unit and browser projects. Off the
  critical path; do not investigate without a ruling from Neil.
- **`--reporter=basic` is not a valid vitest v4 reporter.** Use the default.
- **`chromadb` is deliberately absent from the bootstrap.** `VectorDBService`
  degrades and warns; the warning is expected output.
- **No live Postgres is needed for the financial suite.**
  `test_financial_transaction_query` builds SQLite in a temp directory.

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
    Postgres by `a9e0d29`. Remainders:
    - ~~**Frontend data layer for `GET /api/financial/ledger`.**~~ **Done,
      `fd88318`.**
    - ~~**The ledger screen itself.**~~ **Done, `94af112`.**
    - **Mounting it.** The small remaining piece, and the obvious next unit.
      `LedgerPanel` has no caller outside its own test — verified by grep, not
      assumed: its only other mentions are its own definition and a docstring
      line in `LedgerTable.tsx`. Nothing in
      `src/features/financial/components/FinancialPage.tsx` or any route renders
      it, so the screen exists but is unreachable in the running app. Needs a
      decision on where it sits — most
      likely alongside the existing Neo4j-backed financial view rather than
      replacing it, since the two read different stores and the distinction is
      the point. **Ask Neil before choosing the placement.**
    - **Wiring `ingest_native_reading` into production.** The larger piece.
      Neil's ordering ruling was frontend first.

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

**Is content-hash de-duplication meant to be call-scoped only?** Still unruled.
`document_content_hashes` disambiguates duplicate content within one
`record_transactions()` call but not across two separate calls to the same
document.

**Capability with no route to the user.** `exhibit.py` and `tracing.py` remain
unrouted. Item 12's route-to-user gap is now nearly closed: the data layer and the
screen both exist, and only the mount is missing.

**Provenance of `exhibit.py`.** Unchanged: confirmed valuable, but it came from a
proposed build order, not a stated Owl requirement.

### New this session

**Where does the ledger screen mount?** Not a blocker for the unit that landed,
but it is the first question the next unit has to answer, and it is a placement
decision rather than a technical one. Noted under item 12 above.

---

## Standing flags

- **The Postgres ledger has no production writer.** `ingest_native_reading` has
  no caller outside its own test file. The screen committed this session is
  correct and tested, but against real data it will draw its empty state until
  the wiring item lands. Neil was told this before the ordering ruling and ruled
  frontend first anyway; do not reopen it, but **do not let the empty screen be
  mistaken for a defect.**
- **Nothing mounts `LedgerPanel` yet.** Two units of work are now reachable only
  from their tests. This is the whole of what remains before item 12 closes.
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
