# Loupe build state

Where the work stands. Rewritten whenever a unit lands. Durable rules live in
`CLAUDE.md` at the repo root, not here.

**Last updated:** 5 September 2026 (records the wiring plan, `c88533f`)

---

## Position

- **Branch:** `integration/evidence-main-reunion`
- **Head when this was written:** `c88533f`
  (`c88533fe3d6f03eeff751a2cf13d36d78362a8cd`), "The wiring plan: sixteen units
  to connect a built subsystem to its interface", parent `ba69e7c`. **Confirm the
  real tip with `git log --oneline -5`** at the start of every session rather
  than trusting this line.
- **Nothing is pushed.** Push is blocked; Neil pushes.
- **The build order now lives in `docs/loupe-wiring-plan.md`,** not in this file.
  Read it before picking up work. It is an agreed plan and is not to be
  resequenced without a ruling from Neil.

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

79 commits since `c4246c0` (27 August), counting `c88533f`.

Backend unchanged for two sessions; these figures were measured then:
`backend/services/financial/` **44 modules**, **32,452 lines**;
`backend/tests/test_financial_*.py` **47 files**, **3,057 tests**.

---

## What this session did

**No code.** Two read-only audits and an agreed plan, committed as `c88533f`
(`docs/loupe-wiring-plan.md`, 200 lines, one file).

The session began on the mount question left by the previous one and did not stay
there. Neil pushed back twice — "explain the choice better", then "you're still not
explaining the problem here" — and the second was right. The mount was not the
problem. **Nothing writes to the ledger**, so the screen would have drawn its empty
state wherever it was put.

### The finding, traced not assumed

- `ingest_native_reading` (`services/financial/native_ingest.py:165`) is referenced
  only by its own export lines. **Zero production callers.**
- `record_transactions` is the only thing that constructs a `FinancialTransaction`
  row (`transactions.py:661`). Its only production caller is `native_ingest.py:240`,
  inside `ingest_native_reading`.
- `routers/financial_ledger.py` registers exactly one route, `GET /ledger` at line
  49. **There is no POST anywhere** that ingests.
- `projection.py` — ledger rendered into Neo4j, the module that states Postgres
  holds the ledger and the graph is a derived view of it — also has **zero
  production callers**. So today's Neo4j financial view is not a projection of the
  record. It is an independent write.

### Why it was never cut, from the source that says so

Two docstrings describe the missing path.

`evidence-engine/app/pipeline/financial_route.py` says its own detection stage "is
a backstop, not the main road", that the routing that matters happens before upload
where "the interface sends it to the ledger", and closes with "this stage decides;
the ledger path ingests."

`native_ingest.py` opens by explaining that its seam between reading and writing
sits where it does so "a file can be read, described and shown to a reviewer before
a single row is stored, **which is what the precheck dialog is for**."

Neither the ledger path nor the precheck dialog exists. Grep for `precheck` across
the whole repo returns exactly one hit: that docstring line.

Everything else is there. Backend route-check (`routers/evidence.py:1318`), the
frontend that calls it (`features/evidence/api.ts:123`, `use-route-checks.ts`,
`use-guarded-process.ts`), the badge (`RouteBadge.tsx`), the gate, the four parsers,
the writers, the read path. **A bank file is correctly identified, correctly held,
and then has nowhere to go.** `ProcessHoldDialog.tsx` says exactly this about
itself: the only choice it offers is send the others or send nothing.

### The two audits

**Backend export surface.** A script parsed `__all__` from
`services/financial/__init__.py` via `ast`, then grepped each symbol across
`backend/` excluding `venv/`, `__pycache__/` and `tests/`, discarding hits inside
the package. **676 exported symbols. 37 matched outside. 639 did not.** Several of
the 37 are false positives — `record`, `history`, `place`, `trace`, `normalise`,
`capture`, `describes`, `attribute` are ordinary words matching unrelated code.

There are **five production doors** into 41 modules and every one is a read or a
render: `routers/financial.py:18`, `routers/financial_ledger.py:24`,
`routers/evidence.py:37`, `routers/evidence.py:1347`,
`services/financial_export_service.py:18`.

**Frontend components.** Of eighteen in `features/financial/components/`,
seventeen are imported and reachable from `FinancialPage`. **`LedgerPanel` is
imported by nothing.** Counting bare name occurrences gets this wrong — `LedgerPanel`
has two, both docstring mentions inside `LedgerTable.tsx`. Grep for
`import .*\bName\b` instead.

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

### Verification

Nothing to run. The session wrote one markdown file and touched no code. Every line
number and module location in the plan was checked against source before the commit,
including one that was wrong on first writing: `coverage_from_continuity` lives in
`correlation.py:704`, not in `continuity.py`. The plan says so.

---

## Durable facts, kept so no one rediscovers them

The bootstrap, the baselines, the `VITE_CACHE_DIR` requirement, the playwright
install, the storybook limitation and the git procedure all live in
**`CLAUDE.md`**. Deliberately not duplicated here.

### New this session

- **Every Bash command needs its own absolute `cd`.** Already in `CLAUDE.md`;
  repeated because it was broken twice this session. Once it worked by luck. The
  second time it ran `grep` in the wrong directory and then **hung for the full two
  minute timeout**, which does not look like a missing `cd` at all.
- **`backend/venv/` poisons every repo-wide grep.** A search for `projection`
  returned 53KB of unrelated networkx source. Always pass
  `--exclude-dir=venv --exclude-dir=__pycache__`, and `--exclude-dir=tests` when the
  question is whether something is wired in production.
- **Counting bare name occurrences does not tell you whether a component is
  mounted.** `LedgerPanel` has two occurrences outside its own file and both are
  docstring mentions. Grep for `import .*\bName\b` and list the files.
- **`ast` plus `grep` is a cheap and reliable wiring audit.** Parse `__all__` from a
  package `__init__.py`, grep each symbol across the caller tree, discard hits inside
  the package. Watch for symbols that are ordinary English words; they need reading
  by eye.
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

**Superseded. The order now lives in `docs/loupe-wiring-plan.md`,** committed as
`c88533f`, on Neil's instruction: "I need you to build everything. Have a think
about the best order and make this the plan and stick to it."

Sixteen units in four phases. One unit per session, finished, tested and committed
before the next begins. **Do not reorder without a ruling.** If a unit turns out to
depend on something later in the list, stop and ask.

- **Phase 1, make rows exist** — precheck endpoint, ingest endpoint, the interface
  action on a held file, mount the ledger. Nothing in the other three phases can be
  verified against real data until this lands.
- **Phase 2, make the rows trustworthy** — runs, quarantine, reconciliation,
  adjudication and proof class, duplicates, suspect amounts, locators.
- **Phase 3, make the ledger the source of the graph** — projection, continuity and
  coverage, linkage and correlation and flow.
- **Phase 4, get it out** — exhibit and export, tracing.

**Next unit: Phase 1 item 1, the precheck endpoint.**

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

**Correction versus re-ingestion.** Unchanged, still open, still blocking item
11. Proposal on the table (a correction triggers a genuine re-run of the balance
identity; only a re-run that closes moves the class), not accepted.

**Is content-hash de-duplication meant to be call-scoped only?** Still unruled.
`document_content_hashes` disambiguates duplicate content within one
`record_transactions()` call but not across two separate calls to the same
document.

**Capability with no route to the user.** Now measured rather than estimated: **639
of 676 exported symbols** are reached from nowhere outside the financial package.
`exhibit.py` and `tracing.py` were only the two we had noticed. The wiring plan is
the answer to this and it no longer needs a ruling.

**Provenance of `exhibit.py`.** Unchanged: confirmed valuable, but it came from a
proposed build order, not a stated Owl requirement.

### New this session

**Where does the ledger screen mount?** Still unanswered, but no longer urgent — it
is Phase 1 item 4, after rows exist. When it comes up, two facts constrain it, both
verified: `FinancialPage` early-returns at lines 315 and 323 on the **Neo4j** query,
so a nested tab is unreachable exactly when a freshly ingested case has ledger rows
and no graph; and the persisted `mainView` enum in `financial.store.ts` has no
`version` and no `migrate`, so adding a tab value needs a migration or it reads a
stale persisted value it does not recognise. A sibling route is the current
recommendation. **Its one real cost is two financial-looking entries in the case
sidebar,** where Financial is currently shortcut 5 of 8.

**Should the precheck dialog be built as the design describes it?** The plan assumes
yes, because `native_ingest.py` names it and the seam exists for it. Flagged rather
than treated as settled, since it is the only part of Phase 1 that is inferred from
a docstring rather than from an existing caller.

---

## Standing flags

- **The Postgres ledger has no production writer**, and this is now the top of the
  build order rather than a background fact. `ingest_native_reading` has no caller
  outside its own test file, `record_transactions` is reachable only through it, and
  `financial_ledger.py` exposes no POST. Until Phase 1 lands, `GET /api/financial/ledger`
  returns zero rows on every real case and the ledger screen draws its empty state
  wherever it is mounted. **Do not let that be mistaken for a defect in the screen.**
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
