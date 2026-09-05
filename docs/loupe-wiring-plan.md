# The wiring plan

The financial subsystem is built and almost entirely unreachable. This file says
what is unreachable, in what order it gets connected, and why that order and not
another. It is the agreed plan. A session picks up the next unwired unit and does
not reorder it without a ruling from Neil.

Companion to `docs/loupe-build-state.md`, which says where the work stands today.
This file says where it is going.

---

## What the audit found

Two audits, both read-only, both run against the working tree at `ba69e7c`.

**Backend.** `backend/services/financial/__init__.py` exports **676 symbols**. A
script parsed `__all__`, then grepped each symbol across `backend/` excluding
`venv/`, `__pycache__/` and `tests/`, discarding hits inside the financial package
itself. **37 matched outside the package. 639 did not.**

Several of the 37 are false positives: `record`, `history`, `place`, `trace`,
`normalise`, `capture`, `describes` and `attribute` are ordinary English words that
match unrelated modules. The symbols genuinely reached from outside are
`LedgerQueryError`, `list_transactions`, `to_view`, `attach_transaction_locators`,
`check_case_files`, `PageRenderError`, `render_page_png`, `manifest_for`, `Money`,
and a handful of model and enum names.

There are **five production doors** into a 41-module package, and every one of them
is a read or a render:

| Caller | Imports |
| --- | --- |
| `routers/financial.py:18` | `attach_transaction_locators` |
| `routers/financial_ledger.py:24` | `list_transactions`, `to_view`, `LedgerQueryError` |
| `routers/evidence.py:37` | `render_page_png` |
| `routers/evidence.py:1347` | `check_case_files`, `summarise` |
| `services/financial_export_service.py:18` | `manifest_for` |

**Frontend.** Of the eighteen components in `features/financial/components/`,
seventeen are imported and reachable from `FinancialPage`. **`LedgerPanel` is
imported by nothing.** It and `useLedgerTransactions` are built, tested and mounted
nowhere.

---

## The problem the order has to solve

`financial_transactions` has no production writer.

The chain was traced by reading it. `ingest_native_reading` is defined at
`services/financial/native_ingest.py:165` and is referenced only by its own export
lines. `record_transactions`, which is what actually constructs a
`FinancialTransaction` row (`transactions.py:661`), has exactly one production
caller: `native_ingest.py:240`, inside `ingest_native_reading`. So the only path to
a stored transaction runs through a function nothing calls.

`routers/financial_ledger.py` registers one route, `GET /ledger` at line 49. There
is no POST. Nothing anywhere exposes ingestion over HTTP.

The design intended otherwise, and says so in two places.
`evidence-engine/app/pipeline/financial_route.py` states that its own detection
stage "is a backstop, not the main road", that the real routing happens before
upload where "the interface sends it to the ledger", and that "this stage decides;
the ledger path ingests." `native_ingest.py` opens by explaining that the seam
between reading and writing sits where it does so "a file can be read, described and
shown to a reviewer before a single row is stored, which is what the precheck dialog
is for." Neither the ledger path nor the precheck dialog exists.

What does exist is the whole of detection. The backend route-check endpoint
(`routers/evidence.py:1318`), the frontend that calls it (`features/evidence/api.ts:123`,
`use-route-checks.ts`, `use-guarded-process.ts`), the badge that labels a bank file
in a file list (`RouteBadge.tsx`), and the gate that refuses to send one to the
document pipeline. A native bank file is correctly identified, correctly held, and
then has nowhere to go. `ProcessHoldDialog.tsx` says this about itself in its own
docstring: the only choice it offers is to send the other files or send nothing.

So the ordering constraint is not a preference. Every reviewer capability in the
639 operates on rows. Until rows exist, each one can be built but none can be seen
to work, and the ledger screen already built renders its empty state on every real
case. **Ingestion comes first because nothing downstream can be tested against
reality until it lands.**

---

## Build order

Sixteen units in four phases. One unit per session, tested and committed before the
next begins, per the working agreement. Each unit starts by reading its modules
rather than trusting this summary of them; the phases below name what to read, not
what the code does.

### Phase 1 — make rows exist

Nothing in Phase 2, 3 or 4 can be verified against real data until this phase is
done. It is not the largest phase and it is not optional.

**1. Precheck endpoint.** `POST /api/financial/precheck`. Reads an evidence file's
bytes, calls `detect_format` and `read_native`, calls `describe_subjects`, returns
what the file says it holds. Stores nothing. Resolves the file the same way
route-check does, through `_resolve_stored_path` on rows scoped to a case the caller
may view. Read: `native.py`, `native_subjects.py`, `dates.py` for `CenturyWindow`.

**2. Ingest endpoint.** `POST /api/financial/ingest`. Opens an ingestion run
(`open_ingestion_run`, `runs.py:288`), calls `ingest_native_reading`, terminates the
run on both paths. Surfaces the four documented failures as distinct outcomes rather
than one error: `IngestionError`, `UnattributableRowError`, `ContradictoryPeriodError`,
`SubjectError`. Permission bar is `evidence:upload`, not `case:view`, because this
writes. Read: `native_ingest.py`, `runs.py`, `transactions.py`, `documents.py`,
`accounts.py`, `periods.py`.

**3. The interface sends it.** A precheck dialog showing what the file holds before
anything is stored, and a "Send to ledger" action on the held rows in
`ProcessHoldDialog`. This is the missing half the dialog's docstring describes.
Read: `use-guarded-process.ts`, `ProcessHoldDialog.tsx`, `financial-route.ts`.

**4. Mount the ledger screen.** `LedgerPanel` becomes reachable. Placement decided
when we get here and not before: `FinancialPage` early-returns at lines 315 and 323
on the Neo4j query, so a nested tab is unreachable when the graph is empty, which is
exactly the state a freshly ingested case is in. A sibling route is the current
recommendation. The persisted `mainView` enum in `financial.store.ts` has no
`version` and no `migrate`, so adding a tab value needs a migration or it will read
a stale persisted value it does not recognise.

### Phase 2 — make the rows trustworthy

Every unit here is a reviewer capability that acts on stored rows. Ordered so that
each one's inputs are already visible when it lands.

**5. Ingestion runs.** `RunCounts`, run status, `reap_stale_runs`. What happened
during an ingest, and what was left half-done by one that died. Comes first in this
phase because it is the record of the thing Phase 1 just built, and a failed ingest
is otherwise invisible.

**6. Quarantine.** `quarantine_transaction`, `release_transaction`, `would_rescue`,
`localise`. A row held out of the ledger, why, and what would let it back in. The
ledger endpoint already defaults to `admitted`, so quarantined rows are currently
written and then never shown.

**7. Reconciliation.** `reconcile_period`, `evaluate_identity`, `total_transactions`,
`read_header_totals`, `infer_convention`. Whether the rows add up to what the
statement printed. This is the check that says a document was read completely.

**8. Adjudication and proof class.** `assign_proof_class`, `requires_adjudication`,
`record_admission`, the decisions surface. Proof class is computed and never set by
hand; the interface shows it and shows what an adjudication changed, and never
offers a control that sets it.

**9. Duplicates.** `find_groups`, `resolve_duplicates`, `cross_matter_sightings`.

**10. Suspect amounts and corrections on ledger rows.** The settled rule applies:
flag, cite back to source, let the analyst confirm or edit; both readings stay
visible; only the corrected value feeds sums, flows and searches.

**11. Locators on ledger rows.** `transaction_locators`, `attach_transaction_locators`.
`render_page_png` is already wired for the Neo4j view; this extends the same
source-highlight path to relational rows.

### Phase 3 — make the ledger the source of the graph

**12. Projection.** `project_case`, `ProjectionPlan`, `PREFLIGHT_CYPHER`,
`interpret_preflight`, `RECOMMENDED_CONSTRAINTS`. `projection.py` states that
Postgres holds the ledger, that the graph is a derived view of it, and that only
`admitted` rows are drawn. It has zero callers, so today's Neo4j financial view is
not that derived view. Closing this makes the existing `/api/financial` screens a
projection of the record rather than an independent write. It sits after Phase 2
because a projection of unreviewed rows would need redrawing after every
adjudication.

**13. Continuity and coverage.** `continuity.py`, plus `coverage_from_continuity`,
which lives in `correlation.py:704` and not where its name suggests. What span the
evidence actually covers and where the holes are.

**14. Linkage, correlation and flow.** `linkage.py` (`link_transactions`,
`link_exact_identifiers`, `link_probabilistic`), `correlation.py` (`correlate:1312`,
`correlate_all:1449`, `apply_decisions:1539`) and `flow.py` (`analyse`,
`collapse_mirrors`, `entity_options`). Money movement between parties. Last in the
phase because it consumes the projection and the coverage.

### Phase 4 — get it out

**15. Exhibit and export.** `tag_exhibit`, `may_bear_summary`, `manifest_for` beyond
its current single use.

**16. Tracing.** `compare_doctrines`, `Doctrine`, `TraceResult`.

---

## Rules for working this plan

- One unit per session. Finished, tested, committed, state file rewritten.
- A unit starts by reading its modules. Nothing in this file is a substitute for
  the source, and several of the later phases were grouped from symbol names rather
  than from reading, which is exactly the kind of assumption that has cost us before.
- Do not reorder. If a unit turns out to depend on something later in the list, stop
  and put the question to Neil rather than resequencing quietly.
- Both gates green before a commit: the backend financial suite at its current
  baseline, and the frontend unit, browser, `tsc -b` and eslint runs.
- A new export from `services/financial/__init__.py` must be added to
  `backend/tests/test_financial_exports.py`.
