# Loupe build state

Where the work stands. Rewritten whenever a unit lands. Durable rules live in
`CLAUDE.md` at the repo root, not here.

**Last updated:** 1 September 2026

---

## Position

- **Branch:** `integration/evidence-main-reunion`
- **Head when this was written:** `0d6b399`, "Carry a per-transaction locator
  through the transaction writer". The commit carrying the current revision of
  this file sits one above that, so **confirm the real tip with
  `git log --oneline -5`** at the start of every session rather than trusting
  this line.
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

60 commits since `c4246c0` (27 August). `backend/services/financial/` is 41
modules, 31,819 lines by `wc -l`. `backend/tests/test_financial_*.py` is 43
files, 40,807 lines, **2,993 tests**.

### Facts established this session, so no one rediscovers them

- **Suite baseline is now 2,993 tests, FAILED (errors=1, skipped=9)**, the one
  error still the long-standing `jose` ModuleNotFoundError via
  `services/auth_service.py:10`. Before this commit it was 2,988 with the same
  error. Any other failure is new.
- **The item-10 design ruling, and why.** Neil ruled ("go with deliberate")
  that `TransactionDraft.locator` is **required with no default**. A caller
  with nothing to say passes `Locator(kind=LocatorKind.unlocated)` explicitly.
  Reasoning that carried the decision: a default of `unlocated` would make a
  call site that forgot to thread position data through indistinguishable from
  a reader that tried and failed, and the count of unlocated rows is a defect
  measure only while those two stay apart. Same reasoning `locators.capture`
  gives its `space` argument no default. Migration cost was measured before
  proposing: exactly one production constructor site (`native_ingest.py`,
  which already held a real locator) and two test `draft()` helpers, one
  `setdefault` line each.
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
- **`ingest_native_reading` still has no production caller** (one of the four
  capability-with-no-route instances). Its refusals (`IngestionError` family,
  and now the draft's locator refusals) are development-time guardrails; the
  user-visible artefact of item 10 is the honest `unlocated` marking that item
  12 will surface.
- **Test environment rebuild.** The sandbox starts with no backend deps. Full
  `pip install -r requirements.txt` fails because `numpy==2.3.5` needs Python
  ≥3.11 and the sandbox is 3.10.12. The financial suite runs on a selective
  pinned install (`--break-system-packages`): SQLAlchemy 2.0.46, pydantic 2.12.5,
  pydantic_core 2.41.5, fastapi 0.123.9, httpx 0.28.1, neo4j 5.28.2,
  python-dotenv 1.2.1, requests 2.32.5, psycopg[binary] 3.2.13, openai 2.9.0.
  **Do not install python-jose**: leaving it out is what reproduces the
  documented baseline fingerprint (errors=1 on `jose`).
- Stale `/tmp/loupe*.index` files from earlier sessions cannot be removed;
  the commit procedure works fine with a fresh name per session
  (`/tmp/loupe_item10.index` this time). Pick a fresh index filename if `rm`
  refuses.
- **The exports guard needs no edit for a new name from an existing module.**
  It is structural (AST over `__init__.py`); it passed unchanged when
  `LOCATOR_PROVENANCE_KEY` was added to the `transactions` import block and
  `__all__`.

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

11. Correction storage. The corrected value is canonical, the machine's original
    stays immutable beside it, and the ledger records who, when and why.
    **Blocked on an open question, below.**

12. **Next candidate** (unless Neil rules on the correction question first, or
    redirects to wiring). UI: transaction review with click-through to the
    highlighted region of the source page. This is where `suspect_amounts` and
    the row locators gain their first consumer; until then both are
    built-but-unwired capability. The reader opens
    `provenance[LOCATOR_PROVENANCE_KEY]` via `Locator.from_json`, and
    `SourceRectangle.as_fractions` exists for rendering at any zoom.

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

**Capability with no route to the user.** Four instances, a pattern rather than a
coincidence: the document reader (rows are recovered and nothing downstream consumes
them, item 1), `exhibit.py` (984 lines, no API route, no screen), `tracing.py` (no
caller outside its own package), and `suspect_amounts.py` plus now the row locators
(committed, tested, no consumer until item 12). Both exhibit and tracing have since
been confirmed as wanted, so the question is narrower now: whether the next block of
work is new capability or connecting up what already exists. Item 12 would consume
two of these at once.

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
- **`services/triage_processors/text_extractor.py::_extract_pdf` still uses flat
  `pypdf` text**, so the geometry and text-row machinery built for item 1 is not
  reached in production. This is the same dead-path problem as above, one layer down.
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
