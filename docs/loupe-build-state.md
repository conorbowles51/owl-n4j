# Loupe build state

Where the work stands. Rewritten whenever a unit lands. Durable rules live in
`CLAUDE.md` at the repo root, not here.

**Last updated:** 1 September 2026 (third rewrite this date; this one records the
item-12 survey, Neil's sequencing ruling, and the first item-12 unit)

---

## Position

- **Branch:** `integration/evidence-main-reunion`
- **Head when this was written:** `d79199a`, "Item 12, first unit:
  source-highlight viewer component with locator reader". The commit carrying
  the current revision of this file sits one above that, so **confirm the real
  tip with `git log --oneline -5`** at the start of every session rather than
  trusting this line.
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

63 commits since `c4246c0` (27 August) before this one lands.
`backend/services/financial/` is 41 modules, 31,819 lines by `wc -l`.
`backend/tests/test_financial_*.py` is 43 files, 40,807 lines, **2,993 tests**.
Frontend unit suite after this session: **52 files, 277 tests** (was 50/246;
the two new files and 31 new tests are this unit's).

---

## What this session did (third part): item 12 opened, viewer unit landed

The session had already verified the engine wiring and committed two state
rewrites (`72d1b1a` and before it `ffaceb4`); Neil said "continue for now"
rather than ending at that boundary, so item 12 began in the same session.

### The item-12 survey, as read from source

The locator, as of item 10, is written but has **no read path at all**:

- The Postgres ledger (`financial_transactions` table,
  `backend/postgres/models/financial.py:666`) is where
  `record_transactions` lands `provenance["locator"]`. **No router exposes
  this table**, and `ingest_native_reading` has no production caller, so in
  production the table has neither a reader nor a writer yet.
- The UI's transaction screen reads **Neo4j**, via `/api/financial` →
  `neo4j/financial_service.py::get_financial_transactions` (line 183). Its
  Cypher returns `source_document_id`, `source_filename`, `source_page`,
  `source_excerpt`, confidence and correction fields — **no rectangle, no
  locator**.
- `TransactionDetailPanel.tsx` already shows filename/page/excerpt as static
  metadata fields; there is no click-through.
- `PdfPreview.tsx` is a bare `<iframe src=...>`: no page targeting, no
  overlay capability. It cannot highlight anything as it stands.
- One indirect rectangle source does exist in Neo4j: the engine persists
  `table_geometry.per_table` (cell locators) inside `ProcessedArtifact`
  metadata. A future join could reach rectangles that way; noted, not
  pursued.

### Neil's ruling: viewer component first

Presented as a four-way fork (viewer component first / ledger read API first /
wire `native_ingest` first / page-jump-only on the existing screen). Neil chose
**"Viewer component first"**: build the page-render + rectangle-overlay viewer
consuming Locator JSON, fully testable standalone with fixture locators, no
data-store commitment yet — both stores can feed it later.

### The unit that landed (`d79199a`)

Four files under `frontend_v2/src/features/financial/`:

- `lib/locator.ts` — TS mirror of `Locator.from_json`
  (`backend/services/financial/locators.py`), refusal for refusal: unknown
  keys, unknown kinds, rectangle keys on non-rectangle kinds, units other than
  `millipoints`, spaces other than `pdf_displayed`, malformed or impossible
  rectangles, the per-kind coherence rules (`page_only` requires a page,
  `not_positional` refuses one, `unlocated` permits either). Nothing throws:
  `readLocator(payload: unknown)` returns
  `{ok:true, locator} | {ok:false, reason}` with reasons written to be shown
  to an investigator as-is. `normalised(rectangle)` returns fractions of the
  page, matching the backend method, and like the backend never stores them.
- `components/SourceHighlight.tsx` — renders the four kinds honestly plus the
  parse failure, each under its own `data-testid` (`locator-unreadable`,
  `locator-not-positional`, `locator-unlocated`, `locator-page-only`,
  `locator-no-page-image`, `locator-highlight` with
  `locator-highlight-box`). The box is positioned with percentage
  `left/top/width/height` from `normalised()`. **The page image is a prop, not
  a fetch**, because no page-render endpoint exists yet; when one lands the
  caller supplies its URL and the component does not change. The image must be
  the full page — a cropped render would misplace the box.
- `lib/locator.test.ts` (20 tests) and `components/SourceHighlight.test.tsx`
  (11 tests). Test fractions were chosen to be exact in binary
  (quarters/halves of 612000×792000) so percentage assertions are equalities.

Verification: unit suite 52 files / 277 tests all passing, `tsc -b` 0,
`eslint` 0.

### Correction to the previous revision of this file

The item-12 entry (two revisions running) named a backend method
`SourceRectangle.as_fractions`. **No such method exists.** The real method is
`SourceRectangle.normalised()` (`locators.py:170`); confirmed by grep, and the
TS mirror uses the same name.

### Remaining item-12 chunks, in no ruled order

- A page-render endpoint (the image the viewer needs; nothing serves a page
  image today — `PdfPreview` streams the whole file into an iframe).
- The data path: either expose the Postgres ledger read-side, or join to the
  `per_table` locators already in Neo4j, or both. Also unresolved: nothing in
  production writes the ledger yet (`ingest_native_reading` uncalled).
- Wiring `SourceHighlight` into `TransactionDetailPanel` once data and image
  exist.

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
  source whatever produced the row. Item 12's reader consumes this key;
  `frontend_v2/.../lib/locator.ts` is now that reader's parsing half.
- **Locator JSON shape, as `to_json` writes it**: `{"kind": ...}` plus `page`
  when known (omitted, not null), and for `page_rectangle` only `rect`
  `[x0,y0,x1,y1]`, `page_size` `[w,h]`, `units: "millipoints"`,
  `space: "pdf_displayed"`. US Letter is 612,000 × 792,000 millipoints.
- **Engine wiring (verified end to end, 1 September).**
  `evidence-engine/app/pipeline/pdf_extraction.py` wires
  `services.financial.pdf_tables.read_tables` into the case-evidence path via
  `_load_table_reader()` (sys.path insertion, cached, failure surfaced as
  `available: False`). Verified on
  `ingestion/data/60b9367c-.../bank_statements_first_metropolitan.pdf`:
  5 tables, `geometry_summary` `{"tables": 5, "located_values": 224,
  "unlocated_values": 101, "by_source": {"cell_rectangles": 3,
  "table_rectangle_only": 2, "unavailable": 0}, "by_table_source":
  {"drawn_geometry": 3, "text_alignment": 2}}`; `per_table` JSON 63,324 bytes
  for 3 pages, so the transience warning's arithmetic is right and the
  registry's wholesale metadata persistence keeps it live. Triage
  (`services/triage_processors/text_extractor.py`, flat pypdf) is **out of the
  build by Neil's ruling** ("triage not part of build. engine path then
  flag"); triage artifacts are preview-only and never carried into cases.
- **Test environment rebuild.** The sandbox starts with no backend deps. Full
  `pip install -r requirements.txt` fails because `numpy==2.3.5` needs Python
  ≥3.11 and the sandbox is 3.10.12. The financial suite runs on a selective
  pinned install (`--break-system-packages`): SQLAlchemy 2.0.46, pydantic 2.12.5,
  pydantic_core 2.41.5, fastapi 0.123.9, httpx 0.28.1, neo4j 5.28.2,
  python-dotenv 1.2.1, requests 2.32.5, psycopg[binary] 3.2.13, openai 2.9.0,
  and optionally pymupdf 1.28.2. Suite fingerprints, both measured: without
  PyMuPDF `Ran 2993 tests, FAILED (errors=1, skipped=9)`; with it
  `Ran 2993 tests, FAILED (errors=1)`, skipped=0. The one error is the
  long-standing `jose` ModuleNotFoundError. **Do not install python-jose**:
  leaving it out is what reproduces the documented fingerprint.
- **Frontend verification trio**: from `frontend_v2/`, `npx vitest run`,
  `npx tsc -b`, `npx eslint .`. The vitest config has a separate **browser
  project** matching `src/**/*.browser.test.*` which **cannot run in the
  sandbox** (Playwright browsers are not downloaded; it errors at close with
  "Executable doesn't exist"). The unit-project counts are the baseline; the
  browser error is environmental and pre-existing. Eslint here does **not**
  exempt underscore-prefixed unused destructures; use `delete record["key"]`
  on a copy instead of `const { units: _units, ...rest }`.
- Stale `/tmp/loupe*.index` files from earlier sessions cannot be removed;
  the commit procedure works fine with a fresh name per session
  (`/tmp/loupe_item12_viewer.index` this time). Pick a fresh index filename if
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

10a. **Done (1 September, no code).** Wiring investigation closed by Neil's
    ruling: the evidence-engine path is the production consumer of
    `pdf_tables.read_tables` and is verified end to end; the triage extractor is
    out of the build. Two defects recorded (engine docstring, recovered-chunk
    rendering). Nothing further to wire on this front.

11. Correction storage. The corrected value is canonical, the machine's original
    stays immutable beside it, and the ledger records who, when and why.
    **Blocked on an open question, below.**

12. **In progress — first unit landed (`d79199a`).** UI: transaction review
    with click-through to the highlighted region of the source page. The
    survey, Neil's "viewer component first" ruling, the landed unit and the
    remaining chunks are in the session section above. This is where
    `suspect_amounts` and the row locators gain their first consumer.

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

**Capability with no route to the user — narrowed again this session.** What
remains without a route: `exhibit.py` (984 lines, no API route, no screen),
`tracing.py` (no caller outside its own package), and `suspect_amounts.py` plus
the row locators (committed, tested; the viewer that will consume the locators
now exists but is not yet wired to data). Item 12's remaining chunks close the
locator half.

**Which store feeds the viewer.** Deliberately left open by the "viewer
component first" ruling: Postgres ledger read API, a Neo4j `per_table` join, or
both. Also whether wiring `native_ingest` into production comes before or after
the read side. Neil has not ruled.

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
  was verified end to end on a real document on 1 September. The earlier revision
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
- **(1 Sept, wiring verification):** the engine docstring in
  `evidence-engine/app/pipeline/pdf_extraction.py` claims table text is
  byte-identical to the pre-geometry path; false whenever the recovery pass
  replaces a `table_rectangle_only` reading, which is intended backend
  behaviour. Doc fix on the engine side.
- **(1 Sept, wiring verification):** recovered text-alignment chunks
  collapse empty cells in the `" | "` join (losing Debit/Credit distinction in
  text form) and sweep non-tabular footer prose into the table chunk. Geometry
  unaffected; a full diagnosis is in the `72d1b1a` revision of this file.
