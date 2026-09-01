# Loupe build state

Where the work stands. Rewritten whenever a unit lands. Durable rules live in
`CLAUDE.md` at the repo root, not here.

**Last updated:** 1 September 2026 (second rewrite this date; this one records the
wiring verification session)

---

## Position

- **Branch:** `integration/evidence-main-reunion`
- **Head when this was written:** `ffaceb4`, "Rewrite build state: item 10 landed,
  item 12 next candidate". The commit carrying the current revision of this file
  sits one above that, so **confirm the real tip with `git log --oneline -5`** at
  the start of every session rather than trusting this line.
- **Nothing is pushed.** Push is blocked; Neil pushes.

### Uncommitted

- Two stray `.bak` files that should be deleted, not committed:
  `backend/services/financial/export_manifest.py.bak`,
  `backend/services/financial_export_service.py.bak`. **The session workspace
  denies `unlink` for workspace files, so they cannot be deleted from a session.
  Neil has to remove them from his side.** They are untracked and harmless
  meanwhile.

No tracked changes are outstanding. The tree is otherwise clean of build work.

### Scale, measured from git

61 commits since `c4246c0` (27 August) before this one lands.
`backend/services/financial/` is 41 modules, 31,819 lines by `wc -l`.
`backend/tests/test_financial_*.py` is 43 files, 40,807 lines, **2,993 tests**.

---

## What this session did: verified the production wiring, then corrected the record

No production code changed. The session was a survey, a ruling, and a
verification, and its output is this file.

**The premise it started from was half wrong.** The previous revision of this
file carried a standing flag saying the geometry and text-row machinery built for
item 1 "is not reached in production". Reading the source disproved half of that:
`evidence-engine/app/pipeline/pdf_extraction.py` **already wires
`services.financial.pdf_tables.read_tables` into the case-evidence extraction
path**. Only the triage preview extractor is flat. The flag is corrected below,
and the discovery was surfaced to Neil before anything was built on the bad
premise.

**Neil's ruling (1 September, verbatim scope answer: "triage not part of build.
engine path then flag"):** the triage extractor
(`services/triage_processors/text_extractor.py`, flat `pypdf==6.4.0`) stays
untouched and is **not part of the build**. The work was to verify the
evidence-engine path end to end, then correct the flag. Both halves are done.

### The wiring, as read from source

- `evidence-engine/` is a separate package ("ingestion-service",
  `requires-python >=3.12`, its own pyproject declaring `PyMuPDF>=1.25,<2`,
  pytesseract, Pillow, sqlalchemy, neo4j, lxml). It is the case-evidence
  extraction pipeline.
- `_load_table_reader()` inserts the sibling `backend/` dir into `sys.path` and
  imports `services.financial.pdf_tables`; the result is cached, and an import
  failure is remembered and surfaced in metadata as `available: False` with the
  reason, rather than retried or hidden.
- `_extract_native_tables` calls `reader.read_tables(page, page_number)` then
  `reader.chunks_of(tables)`. `_extract_native_tables_unaided` keeps the
  pre-geometry extraction verbatim as the fallback when the reader is
  unavailable.
- `_table_geometry_metadata` lands `available`, `coordinate_space`,
  `geometry_summary`, and `per_table` (each table's `to_json()`) in
  `metadata["table_geometry"]`. The module itself warns that `per_table` is
  transient and heavy (~221 bytes per located value; ~1.52 MB for a 40-page
  statement) and must be bounded or dropped by anything persisting metadata
  wholesale. **The registry does persist `ProcessingResult.metadata` wholesale**
  (`json.dumps` into a Neo4j `ProcessedArtifact` property), so that warning is
  live, not theoretical.
- Triage artifacts never reach cases: `services/triage/ingest_bridge.py` copies
  the **original files** into evidence storage and registers provenance; triage
  `extracted_text` is preview-side working data served only by the triage UI
  (`routers/triage.py`). So the flat triage path and the geometry-aided engine
  path do not feed the same store.
- Engine processors are loaded in `try/except ImportError`; a processor whose
  import fails silently vanishes from the roster. Worth knowing when a processor
  seems to be missing.

### The verification, all passed

- **`pymupdf==1.28.2` installs cleanly on the sandbox's Python 3.10.12** via
  `pip install --break-system-packages`, despite the engine package itself
  demanding ≥3.12. That version is the one all measurements below used.
- **The nine suite skips were exactly the PyMuPDF duck-typing verification
  tests, and all pass against the real library.** Suite fingerprints, both now
  measured: without PyMuPDF, `Ran 2993 tests, FAILED (errors=1, skipped=9)`;
  with it, `Ran 2993 tests, FAILED (errors=1), skipped=0`. The one error is the
  long-standing `jose` ModuleNotFoundError via `services/auth_service.py:10` in
  both. The four geometry test files are 167/167 with zero skips.
- **The exact engine seam was exercised on a real document**:
  `read_tables(page, page_number)` → `chunks_of(tables)` → `geometry_summary` →
  per-table `to_json()`, against
  `ingestion/data/60b9367c-ec0a-4619-b3ba-eb18ddb91bfb/bank_statements_first_metropolitan.pdf`
  (3 pages, fictional bank statement, Date/Description/Reference/Debit/Credit/
  Balance tables). Result: 5 tables, `geometry_summary` =
  `{"tables": 5, "located_values": 224, "unlocated_values": 101, "by_source":
  {"cell_rectangles": 3, "table_rectangle_only": 2, "unavailable": 0},
  "by_table_source": {"drawn_geometry": 3, "text_alignment": 2}}`. Both the
  drawn-geometry pass and the text-alignment recovery pass fired on one real
  document, exactly as designed. `per_table` JSON for those 3 pages: 63,324
  bytes, confirming the transience warning's arithmetic. Table JSON keys:
  `degraded_reason`, `geometry_source`, `table`, `table_source`; a real
  `degraded_reason` observed: "cells (0, 0) and (0, 1) share page area; a click
  in the overlap would resolve to either value".

### Two defects found by the verification, recorded not fixed

Both are additions to the defect list at the bottom; detail here because a fresh
session would otherwise re-diagnose them.

- **The engine docstring's byte-identity claim is false on real data.**
  `_extract_native_tables` claims `result.tables` "must come out of here
  byte-identical to what it was before geometry existed". On the verification
  document, pages 2–3 differ from the unaided path: the drawn pass yielded
  `table_rectangle_only` (a box but no cells), so `read_tables`' recovery pass
  ran, resolved cells, and **replaced** the drawn reading — the backend's own
  documented, measured design (`_resolved_cells` gates on cells resolved, not
  text produced). The behaviour is intended; the engine-side doc overstates the
  contract. Fix is a doc correction on the engine side, not a code change.
- **Recovered-chunk rendering has two text-level flaws** (geometry unaffected;
  every value is still individually located). In the text-alignment chunk on
  page 3: (a) empty cells collapse in the `" | "` join, so
  `"$168,083.48 |  | $552,873.52"` renders as
  `"$168,083.48 | $552,873.52"`, losing the Debit/Credit column distinction in
  text form and making row column counts disagree with the header; (b)
  non-tabular footer prose ("IMPORTANT NOTICES…", bank footer lines) is swept
  into the table chunk. Affects what embedding/readers see of recovered tables.

---

## Durable facts from earlier sessions, kept so no one rediscovers them

- **The item-10 design ruling, and why.** Neil ruled ("go with deliberate")
  that `TransactionDraft.locator` is **required with no default**. A caller
  with nothing to say passes `Locator(kind=LocatorKind.unlocated)` explicitly.
  Reasoning that carried the decision: a default of `unlocated` would make a
  call site that forgot to thread position data through indistinguishable from
  a reader that tried and failed, and the count of unlocated rows is a defect
  measure only while those two stay apart. Same reasoning `locators.capture`
  gives its `space` argument no default.
- **The writer owns the provenance key.** `record_transactions` serialises the
  draft's locator into `provenance["locator"]` (`LOCATOR_PROVENANCE_KEY`,
  exported from the package); a caller-supplied `provenance["locator"]` is
  refused at the draft. The key is the same one `table_geometry` writes cell
  locators under, deliberately, so one reader can open a row's place in its
  source whatever produced the row. Item 12's reader should consume this key.
- **`Locator(kind=page_rectangle, rectangle=...)` needs no separate
  `page_number`**: the page comes from the rectangle, and an explicit
  `page_number` is checked for agreement if given (`locators.py`,
  `__post_init__`).
- **Test environment rebuild.** The sandbox starts with no backend deps. Full
  `pip install -r requirements.txt` fails because `numpy==2.3.5` needs Python
  ≥3.11 and the sandbox is 3.10.12. The financial suite runs on a selective
  pinned install (`--break-system-packages`): SQLAlchemy 2.0.46, pydantic 2.12.5,
  pydantic_core 2.41.5, fastapi 0.123.9, httpx 0.28.1, neo4j 5.28.2,
  python-dotenv 1.2.1, requests 2.32.5, psycopg[binary] 3.2.13, openai 2.9.0,
  and now optionally pymupdf 1.28.2 (see fingerprints above for the effect).
  **Do not install python-jose**: leaving it out is what reproduces the
  documented baseline fingerprint (errors=1 on `jose`).
- Stale `/tmp/loupe*.index` files from earlier sessions cannot be removed;
  the commit procedure works fine with a fresh name per session
  (`/tmp/loupe_wiring_verify.index` this time). Pick a fresh index filename if
  `rm` refuses.
- **The exports guard needs no edit for a new name from an existing module.**
  It is structural (AST over `__init__.py`); it passed unchanged when
  `LOCATOR_PROVENANCE_KEY` was added.

---

## Build order

1–7. **Done.** Through the text-alignment tier, its tests, the package export and
commit `3784dbe`.

8. **Done.** Financial subsystem description for Alex. Delivered 1 September. Held
   all build work while it was in progress. Final shape: two halves, then a separate
   "being built" section carrying the review screen, money over time, tracing,
   following money through intermediaries, and output labelling. The exhibits and
   tracing bullets were cut from the working sections first, on the grounds that
   everything above the last line has to be something she can do today. **The full
   text is not on disk and not in git history**; only this recorded shape survives.
   If Neil pastes it, store it under `docs/`.

9. **Done.** Suspect-amount detection, committed `0910d9f` as one unit:
   `backend/services/financial/suspect_amounts.py`, the `__init__.py` exports, and
   `backend/tests/test_financial_suspect_amounts.py` (55 tests, 12 classes, every
   `Suspicion` member reached end to end through `read_amount`, reading
   invariants, `require_certain` refusals, `to_json` payload shape and ordering,
   `page_text_origin` via duck-typed fakes).

10. **Done.** Per-transaction source locator through the writers, committed
    `0d6b399` as one unit: required `locator: Locator` on `TransactionDraft`,
    writer serialisation into provenance under `LOCATOR_PROVENANCE_KEY`,
    caller-supplied `provenance["locator"]` refused, `native_ingest` passing
    the object, five new tests. Design ruling and reasoning recorded above.

10a. **Done (this session, no code).** Wiring investigation closed by Neil's
    ruling: the evidence-engine path is the production consumer of
    `pdf_tables.read_tables` and is verified end to end; the triage extractor is
    out of the build. Two defects recorded (engine docstring, recovered-chunk
    rendering). Nothing further to wire on this front.

11. Correction storage. The corrected value is canonical, the machine's original
    stays immutable beside it, and the ledger records who, when and why.
    **Blocked on an open question, below.**

12. **Next candidate** (unless Neil rules on the correction question first, or
    redirects). UI: transaction review with click-through to the highlighted
    region of the source page. This is where `suspect_amounts` and the row
    locators gain their first consumer; until then both are built-but-unwired
    capability. The reader opens `provenance[LOCATOR_PROVENANCE_KEY]` via
    `Locator.from_json`, and `SourceRectangle.as_fractions` exists for rendering
    at any zoom.

13. User-defined view tabs. Named snapshots of filter state, persisted, creatable,
    renameable, deletable. Also expose source document type onto the transaction row.

### Parked (agreed with Neil, 1 September)

14. **Money movement over time.** Money flow currently returns one net picture for a
    date range with no period-by-period series and no trend. `flow.analyse()` has no
    date parameter and no bucketing; every row does carry `ordering_date`, so the
    data is there.

15. **Follow the money.** Chain across entities hop to hop: A paid B, B paid C, C
    paid D. Distinct from doctrine tracing, which concerns mixed funds in a single
    account.

16. **Wire up tracing.** `tracing.py` is built and tested with five doctrines. There
    is no caller anywhere outside `services/financial` and its own tests, no API
    route and no screen. Needs a route and a screen where an analyst picks a source
    of funds, names a doctrine, and sees the comparison across all five.

17. **Wire up exhibit tagging**, and carry the tag onto delivered outputs so a
    schedule states its own category, its outstanding disclosure conditions, and any
    unverified row count on the face of the artefact. Nothing currently produces an
    artefact to tag, so an export path has to come first.

Items 14 through 17 were all confirmed as wanted and were included in the message to
Alex under a clearly separate "being built" heading.

---

## Open questions, waiting on Neil

Recorded as open. No answer has been given to any of these.

**Correction versus re-ingestion.** `adjudication.py` holds that only fixing the
reader and re-ingesting can move a document's proof class, because only then does the
arithmetic actually close. Item 11 makes a human-corrected value canonical, which
would appear to move a class by hand. Proposal on the table, not accepted: a
correction triggers a genuine re-run of the balance identity, and only a re-run that
closes moves the class. That keeps the rule that class is never user-settable and
makes a correction a re-ingestion of one row rather than an override. **Neil's call
is wanted before any correction storage is written.**

**Capability with no route to the user — narrowed this session.** The document
reader is off this list: the evidence-engine is its production consumer, verified
end to end. What remains without a route: `exhibit.py` (984 lines, no API route,
no screen), `tracing.py` (no caller outside its own package), and
`suspect_amounts.py` plus the row locators (committed, tested, no consumer until
item 12). Item 12 would consume two of these at once.

**Provenance of `exhibit.py`.** It came from a build order proposed by Claude, not
from a stated Owl requirement. It is 984 lines justified from the rules of evidence
rather than from a need anyone at Owl expressed. Confirmed valuable on 1 September,
but worth remembering how it got written.

---

## Standing flags

- **P0 is unreachable on the current corpus.** No document carries its own control
  totals in a form that qualifies.
- **Half two has only ever run against synthetic ledgers.** Correlation, flow,
  tracing and exhibit have not been exercised against the real corpus end to end.
- **The item-1 geometry and text-row machinery IS reached in production**, at the
  evidence-engine layer (`evidence-engine/app/pipeline/pdf_extraction.py`), and
  was verified end to end on a real document this session. The earlier revision
  of this flag said the opposite and was wrong. What remains flat is the triage
  preview extractor (`services/triage_processors/text_extractor.py`, `pypdf`),
  which **Neil ruled out of the build on 1 September** — triage artifacts are
  preview-only and never carried into cases, so do not reopen this without a
  new ruling.
- **No row in the corpus carries a running-balance column.** 30,570 rows across 325
  documents, not one. This is why the only proof-grade localisation signal is
  unavailable in practice.

---

## Defects raised and not yet ruled on

Small, real, none blocking:

- Model class is named `AdjudicationEvent`, not `Adjudication` (`ef9e33d`).
- Bulk processing above 50 files cannot work: `MAX_BATCH_SIZE = 50` against list
  paging at 250.
- 11 Capital One pages carry a full-page white image XObject, most likely whole-page
  redaction.
- `merging_properties` missing from `_ACTIVE_JOB_STATUSES`, plus a silent
  fall-through in `_sync_db_record_from_job`.
- `safe_float` does `round(f, 2)` and defaults to `0`.
- The `7d8289b` commit message understates what the commit did.
- Append-only is not enforced at the database.
- The p3 early-return limitation.
- `_get_dataset_metadata` uses all-or-nothing legacy detection.
- `execute_cypher_batch` takes unparameterised strings.
- `get_financial_transactions` compares `n.date` as a string.
- `RECOMMENDED_CONSTRAINTS` and `RECOMMENDED_INDEXES` need out-of-band application.
- Two defects in the mutation harness.
- `scripts/categorize_transactions.py:443` hardcodes `national telegraph`.
- `ProcessConfirmDialog.tsx` contains dead code.
- `frontend_v2/node_modules/.__dom_probe_leftover` left behind.
- **New (1 Sept, wiring verification):** the engine docstring in
  `evidence-engine/app/pipeline/pdf_extraction.py` claims table text is
  byte-identical to the pre-geometry path; false whenever the recovery pass
  replaces a `table_rectangle_only` reading, which is intended backend
  behaviour. Doc fix on the engine side.
- **New (1 Sept, wiring verification):** recovered text-alignment chunks
  collapse empty cells in the `" | "` join (losing Debit/Credit distinction in
  text form) and sweep non-tabular footer prose into the table chunk. Geometry
  unaffected; detail in the session section above.
