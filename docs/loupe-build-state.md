# Loupe build state

Where the work stands. Rewritten whenever a unit lands. Durable rules live in
`CLAUDE.md` at the repo root, not here.

**Last updated:** 1 September 2026

---

## Position

- **Branch:** `integration/evidence-main-reunion`
- **Head when this was written:** `2584afd`, "Keep working state on disk instead of
  in a conversation". The commit carrying the current revision of this file sits one
  above that, so **confirm the real tip with `git log --oneline -5`** at the start of
  every session rather than trusting this line.
- **Nothing is pushed.** Push is blocked; Neil pushes.

### Uncommitted

- `backend/services/financial/suspect_amounts.py` — new, untracked, 26.5 KB.
  Module is written and verified. **Tests are not written.**
- `backend/services/financial/__init__.py` — modified, +23 lines, exporting the
  suspect-amounts surface.
- Two stray `.bak` files that should be deleted rather than committed:
  `backend/services/financial/export_manifest.py.bak`,
  `backend/services/financial_export_service.py.bak`.

The next commit is: write `backend/tests/test_financial_suspect_amounts.py`, add the
new exports to `backend/tests/test_financial_exports.py`, run the full financial
suite, then commit the module, the exports and the tests together.

### Scale, measured from git

55 commits since `c4246c0` (27 August). 127 files changed, 80,216 insertions.
`backend/services/financial/` is 41 modules and about 31,773 lines.
`backend/tests/test_financial_*.py` is 42 files, about 40,197 lines, 2,933 tests.

---

## Build order

1–7. **Done.** Through the text-alignment tier, its tests, the package export and
commit `3784dbe`.

8. **Done.** Financial subsystem description for Alex. Delivered 1 September. Held
   all build work while it was in progress. Final shape: two halves, then a separate
   "being built" section carrying the review screen, money over time, tracing,
   following money through intermediaries, and output labelling. The exhibits and
   tracing bullets were cut from the working sections first, on the grounds that
   everything above the last line has to be something she can do today.

9. **Next.** Suspect-amount detection. Module written and verified; remaining work
   is tests, full-suite run, commit. See "Uncommitted" above.

10. Carry a per-transaction source locator through the writers so every row can cite
    its origin.

11. Correction storage. The corrected value is canonical, the machine's original
    stays immutable beside it, and the ledger records who, when and why.
    **Blocked on an open question, below.**

12. UI: transaction review with click-through to the highlighted region of the
    source page.

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

**Capability with no route to the user.** Three instances found, which makes it a
pattern rather than a coincidence: the document reader (rows are recovered and
nothing downstream consumes them, item 9), `exhibit.py` (984 lines, no API route, no
screen), and `tracing.py` (no caller outside its own package). Both exhibit and
tracing have since been confirmed as wanted, so the question is narrower now: whether
the next block of work is new capability or connecting up what already exists.

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
