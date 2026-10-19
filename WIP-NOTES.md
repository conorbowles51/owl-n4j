# r10-copies: WIP notes

Unit: duplicate evidence principle (priority a). Copies are set aside as linked
duplicates, never silently rejected, never asked about when the money is equal,
never deleted. Counts and opaque ids only (truth period ids are file sha256
prefixes); real detail lives under /mnt/owl-data/fin-real/tmp/r10/.

Base: fin/release-1 at f2b80e45. Branch fin/r10-copies. Not pushed, not merged.

## Landed commits

- 97438d41 files whose pages render identically are one document for the copy rule
  - new `services/financial/page_identity.py`: every page rendered at 40 dpi,
    hashed; the ordered page hashes are the file identity. Stored once per file
    on `EvidenceFile.metadata_['financial_page_identity']` with version,
    renderer, dpi, page count and the bytes sha256 it belongs to. Computed by the
    batch worker after reading, outside any lock. Compared only for the same
    version, renderer and dpi and the current bytes (fail closed). Switch:
    `page_identity.ENABLED`.
  - `pending_statement_duplicates`: a statement of a same-document file (same
    bytes or same pages) on the same pages is the same printed statement,
    whatever its reader's bank wording, product type or money. The better proved
    reading is kept (saved, then reviewed, then edited, then ready by itself,
    then earlier retained, then oldest), the other set aside as a linked copy.
    An unreadable copy of a readable original, and a readable copy of an
    unreadable (held) original, are both settled automatically; the held one's
    queue entry shows it is covered by the retained file.
  - `queue_save.save_statements`: busy / seen / in-flight checks also key on the
    page identity, so two page copies cannot both be claimed in one sweep.
  - `prepare_batch_dispositions` re-evaluates items of page-identical files.
  - frontend: basis `identical_pages` and its wording (StatementDuplicateDecision).
- b5c954da one printed statement of one document, however two readers grouped its pages
  - within same-document files, the only statement in each reading for one
    account reference, currency and pair of dates, on shared pages, is the same
    printed statement (readers grouped its pages differently).
- 6dc467b7 two reconciling readings of the same pages with different money go to a person
  - guard: when both readings reconcile by themselves and their money differs
    (compensating misreads), the pair is held for comparison, not set aside.
  - also `backend/scripts/financial_page_copy_census.py` (read-only live census).
- d77997d7 a reading that captured one more printed balance is not a money conflict
  - the guard compares payments, balance convention and the multiset of printed
    balances (one a subset of the other is not a conflict).

## Measurements

Code under test: d77997d7 (archive at /mnt/owl-data/fin-wt/bench-code/r10-copies-d77997d7).
Real runs use a frozen copy of the wave 9 truth (manifest from truth-backup-pre-v01:
728 files, 1,627 periods) because another unit edited the shared truth mid-session,
and `--readings bench/wave9/engine-readings.json`.

### Whole real set, product default (bench r10c-real4) vs bench/wave9

- ready without edits 1,315 -> 1,315; periods lost 0, gained 0 (per truth id)
- wrongly admitted 0; critical-field errors in saved transactions 0 (20,306 from
  1,326 periods, unchanged); duplicate ledger contributions 0 -> 0; printed
  periods saved twice 0; holds kept 5/5
- copies held automatically 164 -> 168 of 171. Newly held: d6e86ea3cc447#1,
  d7736231834a4#1, d9ff0d74d6f9a#1, dbc494dc292a2#1 (set aside as linked copies,
  basis identical_pages). Not held: daf5c8337d9c7#1, ddbf23dd65ecf#1 (held for a
  person to compare, as before) and dcfc8ce1f2afc#1 (offered and saved, as before).
- REAL_EXIT 1 -> 1 ("2 exact copies offered or saved": dcfc offered + saved). See
  Neil decisions 2.
- possible-duplicate checks removed: 21 -> 13 attention items with a duplicate
  reason (8 removed); items set aside 173 -> 177.
- the summary also lists "readiness_update 40". That is the harness stopping its
  readiness drain early: it stops at the first round that settles nothing, and
  each round has a 20 s budget (44 -> 40 in 3 rounds at load ~8; wave 9 took 17
  rounds at load ~2-3). Reproduced on a private copy of the run's database: the
  same sweep settles 2-3 per round, and one unbudgeted round settles all 35 left
  (backlog 0). After that all 40 are still attention, none importable, as in
  wave 9, and the duplicate counts above are from that drained copy (the
  same projection on the wave 9 database gives the 21). No admission changes.

### Whole real set, generic only (bench r10c-generic-only4) vs bench/wave9-generic-only

- ready without edits 896 -> 896; periods lost 0, gained 0 (per truth id)
- wrongly admitted 0; critical-field errors in saved transactions 0; duplicate ledger contributions 0; holds kept 5/5
- copies held automatically 138 -> 139; offered 1 -> 1; saved 1 -> 1 (dcfc8ce1f2afc#1, the scan pair); exit 1 -> 1 (same cause)
- possible-duplicate holds 220 -> 218 (readiness drain completed: 37 -> 0)
- the other 32 copies not held are page-identical pairs (identities recorded for
  all 728 files) where the generic reader reads two sections of the same file as
  one statement period on different pages. That within-file check ("prints
  another statement for the same bank ... on a different page") holds the
  original and the copy alike. Not a copy-rule miss; generic reader work.

### Page identity over the whole truth set (728 files)

- 10 page-identical groups (20 files), identical grouping at 40 and 60 dpi, ~0.7 s/file
- 0 page-identical pairs that are not truth copies
- 19 cross-file truth duplicate periods covered by those groups

### r9 five-file corpus with r9's own readings (bench r10c-five-before / -after4)

- duplicate ledger contributions 58 -> 0; copies held 0/3 -> 2/3
- the remaining copy is dcfc8ce1f2afc#1 (offered and saved), see Neil decisions

### Synthetic corpus (bench-runs/r10-copies-d77997d7)

- 108/125 ready, recoverable 105/108, wrong 0, critical 0 (366 rows), holds 10/10,
  copies held 1/1, duplicate contributions 0, exit 0

### Live, READ ONLY (scripts/financial_page_copy_census.py)

- 1,777 files rendered (0 unrenderable), 7,771 live batch items
- 13 page-copy groups (46 files), all in one case (d5b330d1)
- 114 live items in them: 19 carry a possible-duplicate check today (the checks
  this rule settles once those files are prepared again), 32 already set aside,
  40 saved, 10 ready, 13 other attention
- FINDING: one printed period is admitted twice in live, truth d7d1158e6b261#2
  and its page copy d9ff0d74d6f9a#2 (case d5b330d1), read by two readers with
  different page grouping and product type. Equal payments row for row, so the
  payments are counted twice, in two different ledger accounts. The wave 9 audit
  reported 0 periods admitted twice; the admitted-duplicates detector buckets by
  product type and requires equal content, so it misses this. Fixing it is a
  live write: Neil.

## Tests

- new `backend/tests/test_financial_page_identity_copies.py`, 15 tests on
  generated PDFs: identity ordering and validity, bytes-different copy; unreadable
  copy linked to a readable original; readable copy kept and unreadable held
  original covered; copy in a later batch; different readers; regrouped pages;
  without page identity the copy was saved twice; a different statement with
  equal metadata is not a copy; compensating misreads go to a person (fails
  without the guard); an extra printed balance is not a conflict; an edited
  statement is kept; two different edits go to a person.
- full financial suite at d77997d7: Ran 6,481, failures 2 (the known
  unassigned_statement pair, present on base), errors 6 (all
  test_financial_extraction_release subprocess timeouts under load; that module
  rerun alone: 4 tests OK).
- frontend (as app user): tsc -b 0; vitest unit 2,129/2,130, the one failure a
  60 s timeout in FinancialPage.test.tsx under load, passed on rerun together
  with the StatementDuplicateDecision test.

## Not verified

- live behaviour: no live file has a stored page identity yet. It is recorded
  when a file is next prepared; existing live items are only re-evaluated when
  their batch is prepared again. No backfill was written.
- the exact real dcfc/d8af wording in the queue after a copy is covered (only
  covered in synthetic tests).

- the harness readiness drain stop rule under load (above): a bench run on a
  busy host can report statements as "being updated"; it did not change any
  outcome here, but the stop rule should tolerate a zero round.

## Targets

- REAL_EXIT 1 -> 0: NOT met (stays 1, dcfc scan pair; Neil decisions 2)
- copies held 171/171: NOT met, 164 -> 168 (dcfc, daf5, ddbf; Neil decisions 2, 3)
- duplicate ledger contributions 0: met (real product, generic only, synthetic;
  58 -> 0 on r9's own readings)
- acceptance: 0 wrong admissions (product, generic only, synthetic) met;
  synthetic exit 0 and 108/125 met; no ready period lost against wave 9 (1,315) met

## Next unit

- the admitted-duplicates detector (and the wave audit) should use page identity
  and reader-independent scope, so live double admissions like the one above are
  found.
- `_set_aside_read_copies` for failed readings still compares bytes only.
- a backfill job (read only rendering, guarded write) for page identities of
  live files, if Neil wants existing batches settled without re-preparation.

## Neil decisions

1. Live double admission d7d1158e6b261#2 / d9ff0d74d6f9a#2 in case d5b330d1:
   set one aside (a live write). Recommendation: keep the reading saved first,
   set the other aside as a linked copy, and merge the split ledger account.
2. dcfc8ce1f2afc#1 / d8af2d5c29493#1 are two separate scans of one sheet (other
   resolution), not page copies. A tolerant image comparison could not tell the
   page from the same account's next month, so the rule fails closed and this
   copy is still offered and saved (REAL_EXIT stays 1 for it). Changing that
   needs a rule Neil accepts (for example equal printed money plus equal printed
   reference on any two files).
3. daf5c8337d9c7#1 and ddbf23dd65ecf#1 are the same statements printed to PDF by
   two different programs: not page-identical, held for comparison as before.
