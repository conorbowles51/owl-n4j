# Unit rd-autoapply: fill known answers by themselves once a held statement's reading is current

Branch fin/rd-autoapply, from fin/rg-integrate aa14b1d3. Counts and opaque ids only. Finished by TAKEOVER RUN 1
after the building agent was stopped with the coordinator.

## Design
- autofill_reapply.sweep (switch LOUPE_FINANCIAL_AUTOFILL_REAPPLY, default on, fails closed): background round in
  run_batches_forever, between sweep_save and sweep_backlog. Only held statements whose batch file carries the
  deployed reader's preparation stamp (or held_reprepare's 'unchanged' mark under it), with no investigator work,
  and only when the automatic fills answer every question the statement asks. Writes through
  queue_save.fill_confirmed (System actor, fill-missing mode, basis recorded, undoable). Saving stays with
  sweep_backlog's normal gates.
- field_proposals.automatic_fills: currency only on the account's own saved statements (never the case's usual
  currency), all one currency, nothing printed, and the statement's printed balances continue that account's
  ledger; bank/holder only when the account's saved statements bracket it; never an account number.
- held_reprepare.exact_copies_rekeyed: a held copy with a stale statement key is prepared again when every current
  statement matching a saved period agrees with it exactly (saved_copies.compare), so the copy rule can set it aside.

## Measured (read only, BNB2 waiting 134, simulated with fresh keys)
- Fresh reading alone (the rg-integrate reader + held_reprepare): 29 prepare ready, 18 ready after every case gate.
- Automatic fills: 5 statements receive a value (2 bank, 2 holder, 1 holder on reviewed work); 0 of them become
  ready (each still has unread balances or rows). Truth-checkable 2/2 correct.
- Why the 27-35 target is not met: on the fresh reading the remaining currency questions (16) are all 'case usual
  currency' proposals (weaker basis, kept as one-click confirms per Neil's rule); no same-account currency answer
  remains open.
- Leave-one-out, automatic fills: truth 3,367 fills, 0 wrong. Live 3,210 fills: 2 misses, neither a new wrong:
  (1) one statement saved as MXN on an otherwise all-USD account whose balances continue the USD ledger (in
  production that account is mixed and fails closed; the saved MXN period may itself be a wrong save: open item);
  (2) a saved holder that is a misread line of text (the fill is the correct holder).

## Tests
- test_financial_autofill_reapply.py (new), field_proposals, held_reprepare: 88 pass. Wider targeted set (queue_save,
  review_queue, import_batches, held_settlement, bulk details): 425 pass (building agent's run).

# Unit rd-pagegate: hold statements whose printed page numbering shows pages absent from the file

Branch fin/rd-pagegate from aa14b1d3. Switch LOUPE_FINANCIAL_PRINTED_PAGE_COUNT_GATE (default on). Counts only.
- printed_page_count.missing_pages: "PAGINA n/N", "Pagina n de N", "Page n of N", "HOJA n DE N". Held only when the
  missing printed pages include page 1 (cover: opening balance, summary) or lie between printed pages that were
  read. Unnumbered pages on or between or beside the statement count as wildcards. Pages missing only after the last
  page read are not held: some card statements count inserts in the total that the download never has.
- Blocker kind printed_pages_missing (preparation and admission), cleared by a coverage note; queue reason pages_missing.
- Truth (whole-set bench aqb-216c5a6b readings, 1,962 items): holds exactly the 3 bbva-mexico truth holds, 0 auto
  items. The first version also held 2 auto capital-one-card periods (trailing inserts) and 1 auto bbva-mexico period
  (unnumbered interior page): fixed by TAKEOVER RUN 1.
- Live audit (read only, 4,713 saved items): 11 saved BNB2 BBVA statements in 8 files miss printed page 1 (list
  reader-gaps/saved-missing-pages.json, opaque ids, outside git). Not changed: open decision for Neil.
- Tests: test_financial_printed_page_count 15 + review_queue: 98 pass.

# Unit rg-others: reader gaps, other named banks (Monex, Kapital, Intercam, Scotiabank)

Branch fin/rg-others, base 68d95b20. Counts and opaque ids only. Targets: 32 held statements, 26 files.

## Causes (statement counts)
- Monex 2021 portrait: white-on-blue movement heading lost by OCR, so six unnamed amount columns overflow the
  search (too_many_interpretations): 5 balance items.
- Monex settlement/agreed dates glued ('DD/Mon(DD/Mon)'): no date token, so no movements: 2 items.
- Monex movement line printing no description word (description on the lines under it): 2 "reading" items.
- Kapital/Intercam: movement heading read only in part on one page, plus one stray mark after an amount: 4
  balance items.
- Scotiabank: date read with rule underscores ('DDMON_'), legal name read without its comma: 1 item (the engine
  now proves it; still held because saved corrections belong to an older reading = investigator path).
- OCR lost data the period needs (amount missing, date unreadable): 4 items (Monex USD 3, Intercam MXN 1).
- Kapital brokerage: no currency printed anywhere: 6 items (needs the account-currency decision).
- Monex EUR section with blank currency (opening label read 'Saldo ae inicial'): 2 items. NOT fixed: a reader
  fix makes the EUR section overlap the saved USD import of the same pages (the reading would be offered as a
  replacement of the USD import), so it stays held.
- Holder not identified (postal-code label lost by OCR): 2 items.
- KAPITAL Inversiones: rotated brokerage pages read as scrambled word order, nothing classifiable: 4 files.
- Kapital USD with saved corrections from an older reading: 1 item (investigator path).
- Manual row needing a page (investigator work, not reader): 1 file.

## Code (all behind default-on switches, fail closed)
- statement_engine.py (SHARED): LOUPE_FINANCIAL_PROFILE_COLUMN_ORDER (profile column_order fills unread
  heading roles only when column count equals the order and every read hint agrees);
  LOUPE_FINANCIAL_PARENTHESIZED_SECOND_DATE; LOUPE_FINANCIAL_DATE_RULE_UNDERSCORE;
  LOUPE_FINANCIAL_UNDESCRIBED_CONTINUATION (text-only lines under a dated line with no description).
- statement_engine_profiles.py (SHARED): column_order key + validation; monex-mexico column_order; scotiabank
  match also on the comma-less legal name (8/8 truth Scotiabank readings, no other document).
- statement_import_kapital.py: LOUPE_FINANCIAL_KAPITAL_HEADING_FROM_SECTION (partial heading completed from the
  section's complete heading, positions within 3pt, no other word in the amount area);
  LOUPE_FINANCIAL_KAPITAL_AMOUNT_NOISE (one trailing mark after a whole amount).

## Result (live, read-only assess + reread dry run)
- 11 of 32 held statements now assess ready (proved, 0 problems): Monex 8 (6 balance, 2 reading), Kapital 2,
  Intercam 1. Before: 0. Scotiabank 1 more now proves in the engine but waits on stale saved corrections.
- Truth set (797 readings, product mode): 789 identical, 8 changed; every changed period has 0 wrong, 0 lost
  transactions; 2 periods move from held to ready (Scotiabank 1, Kapital 1, both matching truth exactly).
  Field-level differences: descriptions lose a printed folio / second date (closer to truth descriptions); one
  Kapital period carries one fewer printed running balance (split OCR cell; not wrong); one Intercam period
  (already ready) drops an OCR-damaged credit-total check row.
- Truth set, generic-only mode (LOUPE_FINANCIAL_GENERIC_ONLY=1): 791 identical, 6 changed; 0 wrong, 0 lost;
  6 periods move from held to ready (Monex 5, Scotiabank 1), all matching truth amounts, dates, directions and
  running balances. One BBVA period (other family, shared engine) changes one description only: a
  rule-underscored second date no longer kept in the text (truth description has no date); figures identical.
- Tests: test_financial_statement_engine.py, test_financial_statement_import_kapital.py,
  test_financial_statement_import_monex.py, test_financial_statement_import_scotiabank.py,
  test_financial_engine_reading_cache.py.


---

# fin/rg-refresh: held statements prepared again by themselves after a reader deploy (2026-10-24)

Counts and opaque ids only. Base 68d95b20. Code commit 32d4e9da.

## Why held items stayed stale (live BNB2, read only)
- 27 review batches. 258 held items: 238 in checked batch files, 9 in error files, 11 on a reading that no batch file names.
- 240 of 258 already carried the deployed `reader_release` stamp. That sweep compares only statement keys and the
  review revision. The revision leaves out identity, period and readiness facts, so the sweep recorded these files
  'unchanged' and never prepared them again. The engine campaign skips them too (same engine: reader_not_affected).

## Design
- Fingerprint: `held_reprepare.preparation_stamp()`, a digest of every module under services/financial (py+json)
  and REVIEW_MODEL. `advance_batch` records it as `file['prepared_stamp']` only when statements are actually prepared
  (not when a comparison records 'unchanged'). `prepare_reviews` stores `summary['prepared_assessment']`, a digest of
  each item's assessment before case gates. A file with no stamp, or an item with no digest, counts as stale once.
- Trigger: the batch loop, in the reader-release block (every 120 s), after `reader_release.sweep`.
  1. Hand-off of pending originals.
  2. Selection. Checked batch files that hold a statement under another stamp are judged by
     `recovery_readers.classify(refresh=True)`. All of the campaign's protections apply. Investigator work or a
     review request always protects (this path carries nothing). Originals held in several batches are all or
     nothing through `_group_reason`. A shared reading is left.
  3. Read only, the deployed reader reads the file. Unreadable files are left. A copy of a saved account and
     period, judged on the CURRENT reading, is left. Unchanged statements and assessments are left. Anything else
     is marked pending.
- Hand-off: under the batch locks, all holder batches must be 'review' and the protections are judged again (work
  saved since judging = left). Each chosen batch file then goes to 'processing' with `recheck.reason=held_reprepare`,
  and the batch goes to 'preparing', exactly like `refresh_files`. The worker prepares from saved text and geometry
  (no engine, no OCR). All the normal gates apply after that: prepare_reviews, readiness, overlap trim, copies,
  duplicates and automatic save.
- Pacing:
  - At most `LOUPE_FINANCIAL_AUTO_REPREPARE_AT_ONCE` (default 4) host-wide, counted together with the engine
    campaign's in-flight hand-offs.
  - Nothing is handed off while evidence is being read.
  - Each sweep reads at most 10 originals, within a 20 s budget.
- Visibility: `review_queue._preparing_again` also returns pending marks, so held buckets show "rechecking". Handed
  files are already shown that way as processing files.
- Deploy: all state sits on batch files. Nothing is in the ingestion gate's blocking set (engine jobs, running
  recovery items, uploads). A handed file is ordinary batch work: one bounded turn holds the lease, the loop pauses
  between rounds, and the gate's 120 s turn wait finds that gap. It resumes after a restart. So no exit 75 from this
  sweep, whatever its backlog. Tested with `check_ingestion_idle.active_work`, which gives 0 when pending and 0 when
  handed.
- Switch `LOUPE_FINANCIAL_AUTO_REPREPARE_HELD` (default on). When off, nothing is selected or handed, and pending
  marks are not shown. Any exception leaves files as they are, and the next sweep tries again.

## BNB2 measure (read only, live reader 68d95b20 + this branch)
- Originals judged: 219 (held items 238; the other 20 held items sit outside checked batch files).
  - picked ('changed'): 85 originals / 90 batch files / 93 held items
  - protected: investigator_edits 83 / 87 / 93
  - protected: copy_of_saved (current reading) 22 / 22 / 24
  - protected: duplicate_decision 14 / 15 / 14
  - protected: not_prepared 8 / 16 / 16
  - protected: unavailable 3 / 6 / 3
  - protected: investigator_decision 2 / 2 / 2
  - protected: shared_reading 2 / 2 / 2
- Picked vs stored, field by field, with the LIVE reader: 92 of the 93 items read the same as stored. 1 item differs
  (transaction count, problems, revision), and 0 read ready before case gates. They are picked only because no item
  carries a digest yet (stale once).
- The live reader reads 11 of the 149 reader-gap targets ready. All 11 are protected: 7 copy_of_saved (the current
  period equals a saved account period, so they are true copies; left to the duplicate workflow), 2
  investigator_edits, 2 unavailable.
- With rg-integrate 8b49156d (bbva + unidentified fixes) merged in a temporary worktree, 4 picked targets read ready
  (3 Scotiabank, 1 BBVA). The reread dry-run preview shows the change: the stored key is gone or the period is
  now proved by the reader. So after the next deploy, those reach the queue with no --apply.

## Tests
- New tests/test_financial_held_reprepare.py: 14 pass.
- Targeted run (reader_release, recovery_readers, held_settlement, review_queue(+balances), import_batches,
  queue_save, recovery_campaigns, deployment_recovery, batch_read_stored/projection, reader_recovery_estimate):
  372 pass, 9 fail. The 9 are the same deployment_recovery failures as on base (checked with base code).
- No isolated Postgres exists on this host (55434 is absent). The selector's SQL ran on live Postgres in a
  read-only transaction (the measure above), and a compile check on the Postgres dialect is in the tests.

## Shared-code changes (small)
- recovery_readers.classify / _group_reason: new `refresh=False` keyword argument. The default path is unchanged.
- import_batches: prepare_reviews stores the assessment digest. advance_batch calls record_preparation (2 places).
  run_batches_forever calls the sweep.
- review_queue._preparing_again: adds pending marks.

## Not done / open
- The 7 Santander-query copies: the current reader still reads the exact saved account and period. They need the
  saved-copy set-aside on the CURRENT reading. held_settlement judges the stored item, so the stale key blocks it.
- The 83 investigator_edits originals stay protected as instructed. The refresh path has no carry.
- The first sweep after deploy re-prepares about 90 BNB2 batch files once (no digests yet). That is throttled to 4
  at a time.

# fin/rg-unidentified: reader gaps, statements whose bank was not identified (BNB2, 2026-10-24)

Counts and opaque ids only (file id prefixes). Real values, page images and transcriptions stayed in the session
scratch directory and are not in git.

## Scope

There are 40 held statements in 40 files: reading 15, currency 11, institution 10, unreadable 4. Branch base is live
68d95b20.

## What the 40 files are (each file opened; the page images were checked)

| Group | Statements | Issue in the queue | What it is | Outcome |
|---|---|---|---|---|
| BBVA Maestra PyME / Maestra Dolares PyME, scanned | 18 | reading 12, institution 2, unreadable 4 | Scans (image + OCR), not in the truth set | Not fixable from the saved reading (below). Coordinate: BBVA unit / engine |
| Santander Consulta de Movimientos, digital | 9 | currency 9 | Already read in full by the deployed reader | Stale preparation (below). Coordinate: re-read |
| Scotiabank Mexico, scanned | 4 | institution 4 | 3 copies (identical bytes, 3 batches) of one zero-activity statement, plus 1 with movements | **3 fixed** (Scotiabank chart heading) |
| Intercam Casa de Bolsa brokerage | 4 | institution 2, reading 1, currency 1 | 2 copies of one digital 2022 statement, 1 image statement with investigator work, 1 proved with no printed currency | Coordinate: others unit |
| Santander integral statement | 3 | institution 2, currency 1 | 2 copies of one badly OCR'd image scan, 1 digital statement split over 10 physical pages | Coordinate: Santander unit |
| Santander online "Posicion Global" printout | 1 | reading 1 | A browser printout of the day's balances: no period, no movements. Not a statement | **Fixed**: set aside as not a payment statement |
| BBVA digital | 1 | reading 1 | The reader reads it (ready). It is held by the investigator's own manual row, which needs a page | Not a reader gap (her work) |

None of the 40 belongs to a bank with a reader that the routing failed to reach. Each layout either has its reader
(BBVA, Santander, Scotiabank, Intercam) or is not a statement. Where the bank went unread, the reader did not
recognise the pages: OCR damage (BBVA, Santander integral scans), one OCR'd heading mark (Scotiabank), or a reading
older than the deployed reader (Santander queries).

### BBVA scans (18): why they are not fixable from the saved reading

I checked the page images of all 18. The OCR has three kinds of damage:
- **4: the right edge of the page is cut off in the scan itself.** The period end, balances and amounts are
  truncated in the image (e.g. a balance printed with its last digits missing). No reader can read them from this
  file.
- **7: a dark scanner-noise band covers the right-hand value column.** The balances and the period end are lost
  under it.
- **7: the page is legible, but the English-only OCR garbles it.** It misreads accents (the label "Operacion" read
  with the accented letter dropped), page numbers ("1/5" read as "1.15"), account lines and handwritten ticks. On
  these pages a balance digit can be misread (one "Saldo Final" read with its first digit wrong).
- Several files are also only part of a statement (2 of 6 printed pages; 8 of 12; 1 of 5).

The BBVA reader's identity gate needs the exact title, product, "PAGINA n/m", account and period. None of the 18
meets it, and loosening it would mean taking the account, the period and the balances from garbled OCR (0-wrong
rule). Two of the legible ones (052ad764, 5127a40e) only miss a balance label with its accented letter dropped. That
label belongs to the BBVA unit's reader, so I did not touch it. The real fix for the group is a better OCR reading
of these scans (Spanish model, value-column crop, noise-band handling): that is engine work, not reader work.

**The 4 "nothing could be read" files** (c6db581e, 50ae18d8, aa327762, 9bf457e4) are BBVA scans of this group. They
are **not image-only**: every page has saved OCR text (3.1k to 31.8k characters) and table geometry. Nothing was read
because no reader found a statement period on any page:
- c6db581e, 50ae18d8: the period line is misread, the account number is not read and "PAGINA" is garbled. Each
  file holds only 2 of 6 printed pages.
- aa327762, 9bf457e4: the period end, dates and balances sit under the noise band.

So the queue shows a file-level item with no facts.

### Santander Consulta de Movimientos (9): why they are still held

These are digital. The deployed reader reads all 9 (bank, account, MXN, balances match; `assess` = ready 9/9). They
are held because their batch items were prepared on 2026-10-15 and 2026-10-23, before 68d95b20.

- Recovery run 92802b80 selected 7 of them. A newer release superseded that run ("kept newer_release") before they
  were read again.
- Release 98bfbeae (28fad995) then classified all 9 as `copy_of_saved`, because their stale periods overlap saved
  months.
- So no automatic path prepares them again. A refresh from the saved reading (`financial_reread_file --apply`,
  coordinator) is what applies the current reader. The case-level overlap/duplicate disposition then decides; my
  dry run does not simulate it.

## Fixes (branch fin/rg-unidentified)

1. **Scotiabank zero-activity chart heading** (`statement_import_scotiabank.py`, switch
   `LOUPE_FINANCIAL_SCOTIABANK_FOOTNOTE_MARK`, default on). The chart heading "Otros cargos*" carries a footnote
   asterisk, and the scans read it as a quote glyph. The heading was therefore unmatched and the whole statement
   refused. The fix tolerates exactly one trailing quote glyph on that one heading. Every other check stays as it
   was: five chart amounts each read as zero, equal printed opening and closing, the three pages, the account, the
   period, Moneda NACIONAL, and no movement table.
2. **Online balance position is not a payment statement** (`not_payment_statements.py`, switch
   `LOUPE_FINANCIAL_NOT_PAYMENT_POSITIONS`, default on, which needs `LOUPE_FINANCIAL_NOT_PAYMENT_STATEMENTS`).
   - It applies only when every page of the reading prints the "Posicion Global" title, its balance-position heading
     and its portfolio total.
   - No page may print a period, a movement, a statement title, a debit/credit/deposit/withdrawal word or a
     statement balance label.
   - The reader must have found no statement period, and there must be no payment, no saved review and no restore.
   - It is set aside in the same way as fund statements: never saveable, put back on request, nothing deleted.
   - `held_settlement` uses the new `titled()` pre-check. The import refusal message names the kind.

## Measured

- **Read-only dry run on live**, with `read_statement_import` and `assess` per statement, on the 40 targets:
  - base 68d95b20: ready 10 (the 9 Santander queries and the BBVA digital, all on stale items).
  - branch: ready 13 (adds the 3 Scotiabank) and 1 set aside as not a payment statement.
  - `financial_reread_file` dry run (no `--apply`): the 3 Scotiabank files now read 1 library period each, with
    bank, account and holder; the position file reads 0 periods.
- **Scotiabank truth mini** (8 PDFs, readings reused from r15-scotia-088f9868):
  - switch off: 5/8; switch on: 6/8 (dc3fbbaef34d0#1 saved, equal to truth).
  - Wrongly admitted 0, critical-field errors 0, double counts 0.
  - The one "valid-looking wrong currency" proposal is on held dec16784acb31#1. It is identical with the switch off,
    so it predates this branch.
- **Catalog equivalence on the whole truth set** (797 readings of r14s-whole): the Scotiabank change alters exactly
  1 document (dc3fbbaef34d0: 0 -> 1 zero-activity period, correct dates). The position rule matches 0 of 797. Live
  (all cases, read only): 5 files carry such a page, all in BNB2. 1 is this target; the other 4 are already removed
  or superseded.
- **Tests:** 269 passed, 0 failed (held_settlement, review_recovery, statement_import_scotiabank, statement_progress, statement_import, mexico_no_activity, mexico_movement_scaffold, review_queue). New: a Scotiabank footnote-mark test (marks accepted; a word, a second mark or an amount refused; switch off) and position tests (recognised, 12 refusal variants, never saveable).

## Not fixed (and who should look)

- **BBVA scans (18):** scan damage (above). Engine OCR work. BBVA unit: the dropped-accent balance label in 2 files.
- **Santander queries (9):** coordinator re-read (stale items). Same for the 3 Scotiabank files: recovery classifies
  them `reader_not_affected` (same engine), so they also need `financial_reread_file --apply` to reach the queue.
- **Santander integral (3):** Santander unit.
  - Image-only copies: dates are garbled by OCR.
  - Digital file: `santander_catalog` finds no group, because the printed "HOJA n DE 5" headers fall on alternate
    physical pages only.
- **Intercam brokerage (4):** others unit.
  - The 2022 digital layout is not read by the intercam-brokerage profile ("no printed balances or movement lines").
  - The proved one has no printed currency and its account has nothing saved (Neil's account-currency rule cannot
    fill it).
  - The image one carries investigator work.
- **Scotiabank with movements (1):** the movement table is the off-by-default scaffold. The opening is read without
  punctuation, and the engine proposes the wrong currency (pre-existing). Not changed.
- **BBVA digital (1):** the investigator's manual row needs a page (her work).

---

# fin/rg-bbva: BBVA reader gaps (BNB2 held statements), counts and opaque ids only

Branch fin/rg-bbva from live 68d95b20. Targets: reader-gaps/bbva.json (46 held statements). Private
material (bench runs, mini corpus) under /mnt/owl-data/fin-real/rgb (mode 700).

## Causes (46 statements)

| Cause | Statements | Outcome |
|---|---|---|
| Fund statements (holdings only) listed 'unexplained' | 11 (+1 more held as 'balance') | FIXED (projection) |
| File misses printed pages (printed "page n of m", file holds fewer) | 10 | correctly held, not a reader gap |
| BBVA credit line ("Linea Credito Digital PyME", amounts owed, OCR-garbled summary) | 8 (4 distinct prints) | not built: needs a credit-line (liability) reading with summary interest/IVA as rows; truth: 2 of 4 distinct auto, 1 hold, 1 decision |
| Scanned movement lines whose date has an underscore/hyphen mark ('11/DIC_') | 2 | FIXED for 1 (engine B2 rule); the other still holds on one damaged second date ('{7IDIC_') |
| OCR digit misread in an amount (5 read as 9, chain breaks by exactly the difference) | 2 | not fixable from the saved text (needs a new engine reading) |
| Damaged operation date with a legible settlement date ('OS/MAY' beside '05/MAY') | 2 (+ others inside held files) | NOT built: on 400 BBVA files, 654 of 11,832 movement lines print different operation and settlement dates (5.5%, e.g. 07 vs 05), so the settlement date cannot stand in for a damaged operation date |
| Investigator's earlier saved review on the file | 3 | investigator decision, not reader |
| Account number not read (OCR) | 4 | not reached |
| Other single cases (currency proposal, manual row needs page, 1 no-activity, 1 two-page fragment) | 4 | not reached |

### Fund statements: why the rule did not trigger live
The rule did trigger: all 11 items store `summary.not_payment_statement` (assess, 68d95b20). The listing
projection (`import_batches._checked_batch_items`, coverage stage) re-derived each item's state from its problems
alone; a fund statement has no problem and is never saveable, so it came out 'ready' with can_import False, and
`review_queue.classify` (which looks for not_payment only on 'attention') counted it 'unexplained'. Fix: the coverage
stage keeps such an item 'attention' (follows LOUPE_FINANCIAL_NOT_PAYMENT_STATEMENTS). Live read-only _compute:
unexplained 11 -> 0, not_payment 0 -> 11, every other bucket unchanged. A 12th BBVA fund statement (held 'balance',
stored reading older than 68d95b20) reads as not_payment on a fresh read; it moves on its next re-read.

### Date edge marks (engine, shared code)
`statement_engine._date_parts`: when a token reads as no date, an underscore at either end and a hyphen before an
underscore are stripped and only a day-and-month-name reading is accepted (`'11/DIC_'`, `'-11/DIC_'`, `'13/DIC._'`,
`'27/IMAR_'`). Switch LOUPE_FINANCIAL_DATE_EDGE_MARKS (default on). Changed one existing test expectation: a second
date printed with an underscore ('1O/MAR_', '10/ABR_') now reads as that date, like the same ink without it.

## Measured
- Dry run (fresh reading + assess, worktree, read-only) of the 46: not_payment 12, ready 1 (was 0), held 33.
- Live engine survey, BNB2 files carrying such date tokens (62 files): 17 periods newly proved, 0 lost, 0 read
  differently.
- Truth: 26 distinct tokens in the 797 truth readings change reading, in 8 truth documents. Mini bench on those 8
  (r14s-whole readings, base 68d95b20 vs branch): product 6 -> 7 ready, generic-only 6 -> 7, 0 wrong, 0 critical,
  0 lost (gained d889c7856ad55#1).
- Synthetic (aqb synth readings, branch): 108/125 ready, 0 wrong, held 10/10 (same as base figures recorded).

## Coordinator extras (2 BBVA scans from unidentified.json, files 052ad764 / 5127a40e)
Tried a dropped-accent label rule ('SALDO DE OPERACIN FINAL') in the engine vocabulary and the BBVA reader. It
fixes the label but neither statement proves: 052ad764 prints no recognisable balance labels at all (no profile
match, 'no_movements_or_controls'); 5127a40e has OCR noise between the closing label and its value and damaged
totals ('0.00?'), so closing and the deposit total stay unread. No gain, so the change was reverted (fail closed).

## Tests
test_financial_statement_engine.py, test_financial_statement_import_bbva.py,
test_financial_bbva_capital_one_reading_quality.py, test_financial_held_settlement.py: all pass.
New: DateEdgeMarkTests (4), the listing-projection fund test (2).

## Shared code touched
- backend/services/financial/import_batches.py (coverage stage of the listing projection, 3 lines).
- backend/services/financial/statement_engine.py (`_date_parts`, new switch).

---

# Integration of BNB2 queue units (A2 decisions, B Santander gap, C others)

## Unit A2 notes
# Unit A (Alex queue) — approved Santander query + brokerage currency

Branch fin/aq-a-approved, base f2a52eae. Counts and opaque ids only.

## Code
- statement_import_santander_query.py (switch MOVEMENT_QUERY): online movement query detected by its
  printed title, issuer legal line, 10 header labels repeated identically per page, page "i de N", one
  movement heading table per page. Opening = first printed running balance minus first movement
  (balance_basis printed_opening_after_first_movement); admitted only when printed Saldo Inicial equals
  the first running balance, movements oldest first, counts/totals/closing/running balances all agree,
  every page present, every line on the printed account. Otherwise held (no opening, unresolved row).
  Institution taken from the legal line so the query joins the monthly statements' ledger account.
- statement_engine.py (switch HOLDINGS_CURRENCY) + _BROKERAGE_CASH.holdings_currency: a brokerage cash
  ledger takes the one currency code its holdings table prints; none or several = held.
- statement_currency: 'printed_holdings_currency' accepted for the generic layout.

## Targets (35 items; 20 query, 15 brokerage)
Live mirror (live readings, live items incl. 9 duplicate uploads):
- before: 0 saved / 35.
- after: query 6 saved, 7 copies set aside as duplicates, 7 held overlap (online queries overlap one
  another); brokerage 0 saved.
Fresh read (bench readings, 26 distinct docs): before 0; after 14 proven, 8 auto-saved
(7 query + 1 brokerage), 6 query held overlap. 0 wrong, 0 critical-field errors (194 txns).

## Held, honest reasons
- brokerage 11 docs: no currency printed anywhere on the statement (checked against renders) -> needs a
  decision (case-level/account-level currency rule).
- brokerage 1 doc (opaque 42dc6ddb): opening not printed, identity unread -> held.
- brokerage 5 live items: live reading is an older OCR reading; current engine reading saves 1 of them
  (opaque 62d19a23) after re-read.
- query 7: overlap between online queries of the same account (by design held; needs trim rule decision).

## Truth
13 query docs: visual transcriptions record the derived opening; status unverified -> verified (auto).
Applied to shared truth via real_truth --only (backup truth-backup-pre-aqa); shared status now
verified 806 / not_statement 17 / unverified 5 / settled 4.

## Gates
- synthetic (wave13 readings): base 108/125 ready, branch 108/125, 0 wrong both.
- mini real (product and generic-only): 0 wrong.
- targeted backend tests: 489 + new green.

## Deploy
- No migration. Re-read the 4 stale brokerage live readings with the current engine.
- Readiness refresh sweep picks up held items after deploy.

## Real-set equivalence (in progress at hand-off)
Catalog+currency digest of every real reading (815, readings-w13-plus18), base vs branch code, product
source path. Whole-set harness vs r14s-whole NOT run (10h). Integration must finish this diff:
results private under fin-real/tmp/aqa/equiv-*.jsonl; any differing doc outside the 26 target docs is a
blocker.

# Unit A2 — Neil decisions 2026-10-24: account currency + overlap trim

Branch fin/aq-a2-decisions, base 12e51fc7. Counts and opaque ids only.

## Code
- Rule 1, field_proposals (switch ACCOUNT_CURRENCY): a brokerage cash ledger (holdings_currency profile,
  reading flag brokerage_cash_ledger) printing no currency anywhere gets a currency proposal confirmed
  automatically from its ledger account's saved statements when they give exactly one currency (one saved
  statement suffices), identity exact+unique on two fields, no saved statement on the same dates. Basis
  'account_currency', label "account currency: same account's N saved statement(s)", saved through the
  System details save (audited with the basis). None / several currencies -> stays held (currency).
  A brokerage statement printing a currency (holdings) that differs from its account's -> held
  (statement_detail currency, can_import False) in the batch coverage stage.
- Rule 2, statement_overlap_trim.py (switch TRIM_OVERLAPS), called in read_statement_import for the
  movement-query form: trims only against SAVED statements of the same ledger identity (never waiting
  ones), exact copies/lineage excluded. Overlap rows must match one for one (date, amount, direction,
  running balance). Prefix/suffix trims only; middle cover / mismatch / missing balance -> held for
  overlap with the reason appended to the overlap note. Whole query covered with exact rows -> held
  (fully_covered, not saveable: saving would count twice). Kept rows: opening = running balance after
  last trimmed row (basis running_balance_before_kept_dates), closing on suffix trim = last kept running
  balance, totals = kept sums with printed totals recorded; whole query proved first; kept part re-proved.
  Trimmed rows stay in the reading, excluded, with covered_by (source doc) and reason "Counted once: ...".
  Trim is in the revision (writer re-reads under the case lock -> stale claims 409). Trimmed bounds saved
  as derived. Skipped for a query with a person's saved review; a query saved whole stays whole.
- Ordering: waiting queries rank by (start, end, file, statement); a query's overlap note ignores
  LATER-ranked waiting queries (they trim against it once saved) — batch coverage and import writer.
- Readiness: query items' fingerprint includes the case's saved-state mark; they are re-read when not
  current. queue_save.REVISIT_AFTER_SAVES: the sweep looks at a case's marked files again after any save.
- Harness: worker cycles after sweep saves (readiness -> sweep -> import, up to 12); ledger check scores a
  trimmed period against its kept dates and requires its trimmed rows to be held by another saved
  statement of the account; new metric movements_counted_twice (same account, date, amount, direction,
  running balance in two saved statements).

## Results (0 wrong admissions, 0 critical-field errors, 0 movements counted twice in every run)
- 11 no-currency brokerage docs: before 0 ready (held currency). Fresh read: 7 saved with account currency
  (their account has 1 holdings-currency statement saved, opaque 62d19a23), 4 held (their 2 accounts have
  no saved statement). Live mirror (live readings): 0 — the anchor statement's live reading is stale OCR;
  after its re-read (deploy note from unit A) the 7 follow. Live BNB2 saved brokerage state not checked
  (production reads not permitted to this unit).
- 7 overlap-held query items (live mirror): before 7 held overlap -> after 7 saved trimmed; all 13 distinct
  query periods auto-saved, copies set aside 7/9 as before. Fresh read: before 6 held -> 5 saved trimmed,
  1 held fully_covered (every movement already in a saved, longer query).
- Extended private mini (targets + 21 related docs of the same accounts), unit A code vs branch:
  auto-saved 22 -> 35, lost 0, gained 13 (8 brokerage, 5 query). Both runs flag the same pre-existing
  copy (a reprint whose original is outside the mini corpus) — identical in base.
- Synthetic (wave13 readings): 108/125 ready, 108 auto-saved, 0 wrong — identical to base.
- Tests: 15 targeted files (unit A set + import_batches, queue_save, harness) + 15 further affected files
  + new test_financial_statement_overlap_trim.py (14) + 9 account-currency tests: all green.

## Not done
- Whole-set harness vs r14s-whole not run (shared host); catalog/currency digest unaffected by these
  rules (trim is post-catalog, account currency is a proposal), unit A's equivalence diff still open.
- Removing an import that covers a trimmed query does not re-open the trimmed query automatically:
  find them by covered_by on the trimmed statement's saved request rows.

## Unit B notes
# aq-b-santander: BNB2 waiting statements the bench saves but live holds

Counts and opaque ids only. Scratch evidence (private, mode 700): /mnt/owl-data/fin-real/tmp/aqb.

## Target set
- 64 live held statements in the truth corpus (units B 42, C 22); 50 of them are file-level saved by
  bench r14s-whole ("the 50"); 36 period-level (same dates).
- Live: all 64 held before. 62/64 live readings come from older engine revisions; the deployed engine
  digest is the same in base and in release-1 (390680fa).

## Cause, measured in a disposable batch (no investigator input)
| readings | code | targets ready (of 64) | of the 50 |
|---|---|---|---|
| retained live readings | base f2a52eae | 10 | 10 |
| bench readings (w13) | base | 34 | 32 |
| bench readings (w13) | + wave 14 (390680fa merge) | 37 | 35 |
| fresh current-engine reads (54 originals) | base | 34 | 32 |
| fresh current-engine reads | branch head | 37 | 35 |
- (b) stale engine readings: +24; (a) wave-14 code not deployed: +3.
- (d) person work: 34 targets carry saved progress or review requests by an investigator (must stay held).
- (c) batch/file-level guards: base campaign reasons for the 64: removed 26, investigator_edits 15,
  saved_import 10, duplicate_decision 10, reader_not_affected 2, eligible 1.

## Changes (branch)
- 319293fc merge of release-1 390680fa (wave 14).
- 216c5a6b re-read selection: restart after a removed batch, settled siblings (System-saved or System
  set-aside items no longer protect), failed idle batch members, selection rule in the release id
  (new id statement-recovery-engine-dfc2db02...).
- 7e238245 stale ready listing of a statement already saved is settled.
- 1c514593 / 0ba6ca50 copy_of_saved: held statement whose account (last six digits) and period the case
  already admitted is left for the duplicate workflow (fail closed; caught 2 truth duplicates the
  re-read would have saved and 9 periods admitted under another statement key).

## After (live read-only selection x fresh+branch measurement)
- 64: saved_new 5 (all equal to truth: balances, currency, rows); selected but still held after re-read 7
  (balance/reading 4, currency 2, account+balance 1); not selected: investigator_edits 30,
  copy_of_saved 12, duplicate_decision (person) 6, investigator_decision 2, reader_not_affected 2.
- the 50: saved_new 5; copy_of_saved 10; investigator_edits 27; duplicate_decision 5;
  investigator_decision 2; held after re-read 1.
- Wrong admissions on targets: 0 (2 truth-duplicates protected by copy_of_saved).
- Case-wide selection under branch rules: eligible 51 (base 14), copy_of_saved 47.

## Tests
- 18 targeted backend files: head 529 passed / 20 failed; base 512 passed / 20 failed; the same 20
  fail on base (pre-existing). Engine not touched.
- Synthetic bench (frozen code 216c5a6b; later commits touch only recovery selection): ready 108/125,
  wrongly admitted 0, duplicate ledger contributions 0, held kept out 10/10.
- Whole-set product bench on frozen code: started (bench/aqb-216c5a6b), about 10 h; generic-only not run
  (host shared, 6 CPUs, one bench at a time).

## Carry investigator work onto the re-read (decision 2026-10-24)
- 3771ef7e: statements with saved progress or batch drafts are re-read; her detail/row edits are carried
  onto the new reading (hers win), hand-added rows kept in place, the carried review stays hers (never
  System-saved), her original stays on the earlier reading (carried_from + per-file carry log). A review
  saved after scheduling is refused (work fingerprint). Not carried, stays held with reason: rows not
  aligned, statement/row ambiguous, work in another batch, two different drafts. Person decisions untouched.
  Switch LOUPE_FINANCIAL_RECOVERY_CARRY_EDITS.
- Worked statements in the 25 files of the formerly investigator_edits targets (35): carried 6 (4 exact
  baseline, all System-filled details; 2 unproven baseline, a person's row edits); not carried 29
  (rows_not_aligned 15, work_in_another_batch 5, statement_ambiguous 3, row_ambiguous 1, two_drafts 1,
  plus 4 on the original's source reading).
- The 2 statements carrying a person's carried edits stay held after carrying (row reading checks).
- Final, the 64: ready 8 (all saved, all equal to truth, none already admitted live); held: copy_of_saved 14,
  after re-read 11, sibling work not carried 10, own work not carried 8, duplicate_decision 6,
  investigator_decision 4, reader_not_affected 2, not_all_held 1.
- The 50: ready 8 (saved 8); held: copy_of_saved 12, sibling work not carried 10, own work not carried 8,
  duplicate_decision 5, investigator_decision 4, after re-read 2, not_all_held 1.
- Disposable carry run: 36 saved periods, 36 equal to truth, 0 differ.
- Case-wide live selection under head rules: eligible 111, copy_of_saved 97, saved_import 137.
- Tests head: 18 targeted files + review_carry: 536 passed / 20 failed (same 20 fail on base);
  6 files touching review recovery: 210 passed.

## Release untouched periods of a split file carrying her work (decision 2026-10-24)
- Rule (review_recovery.recovery_state, switch LOUPE_FINANCIAL_RECOVERY_SPLIT_RELEASE): when every
  uncarried earlier record that the new reading cannot place is file-level work, and the new reading names
  several periods, a period proceeds through normal readiness/auto-save only if none of that work touches
  it: no saved row of hers dated in its range (her date, else the earlier reading's date for that row id),
  no overlap with her request's period or any period imported from her reading (no double count), no
  shared row id and no shared page. Any row that cannot be dated, or any named-period work, keeps the whole
  file held as before. Her records are not changed. Released periods record split_from_held_work (held
  review ids, earlier readings, period) on the batch item summary and on the imported source document.
- Measured on the 10 (9 files), read only: all 22 uncarried records are file-level full snapshots of an
  old parse (mostly undated header rows; 21 file-level, 1 named); 0 can be dated, and on every file her
  rows sit on every page of every period of today's reading. Released 0 of 10: all stay held correctly.
- Counts unchanged: the 64 ready 8; the 50 ready 8 (sibling work not carried 10, now held by rule, not
  by default). Wrong admissions 0, lost 0, no live writes.
- Tests: 20 targeted files: 590 passed / 20 failed (the same 20 pre-existing failures); 5 new rule tests.
- Whole-set bench (bench/aqb-216c5a6b) still running at 02:20 UTC (918 of about 1944 batch items).
  Compare when done: python3 /mnt/owl-data/fin-real/tmp/aqb/compare_whole.py /mnt/owl-data/fin-real/bench/aqb-216c5a6b
  (per-period lost/gained vs r14s-whole results-rescored.json; script self-check on r14s-whole: lost 0).

## Do her uncarried records hold real edits? (read only, 2026-10-24 02:35 UTC)
- Script fin-real/tmp/aqb/baseline_classify.py (+ baseline_diff.py, baseline_proxy.py); private output baseline-classes.json.
- Baseline recovery: today's code reproduces the saved-on reading for 1 record only (revision match). Others recovered
  through the account-detail audit (an entry at the same instant: before/after/actor; rows verified unchanged vs her
  previous save on the same revision) or provable work (hand-added rows, row changes between her own saves).
- 48 uncarried records (the 22 sibling + 26 on the worked statements incl. source-reading and row-less drafts):
  a 1, b 4 (audited System fills: holder 2, currency 2), c 31, d 12.
  c: statement details only 25 (holder 16, account 13, institution 12, currency 3 field-touches; audited, by the investigator);
  rows 6 (hand-added rows 15 / 4 x4 records with 1 row changed and 1 row note / 19). d: unaudited first saves on
  readings today's code does not reproduce (no hand-added rows, no notes).
- The 22 sibling: a 1, c 14 (all details-only), d 7. No record carries a statement note; 1 carries a row note.
- Eligible if a/b = "no edits to keep": 3 of the 18 held by uncarried work (3 of 64, 3 of 50: own_work f0e365/77fb6f/
  64a961 statements, System-only fills); 0 of the 10 sibling-held.

## Settle System-only work, carry details-only work with a payment match (decision 2026-10-24)
- e43ecebe, reread_carry.plan_statement (switch LOUPE_FINANCIAL_RECOVERY_DETAILS_CARRY, default on):
  - no edits to keep: every saved record of the statement is System's (a batch draft with no saver counts as
    System only when its request equals a System save) and no person is in its save or detail history ->
    settled, not held; the new reading is prepared like any other.
  - details carried, payments matched: row-by-row carry failed on row alignment, and her work is details only
    (no hand-added row, row note, statement note or confirmation; rows unchanged between her saves). Her
    holder/account/institution/currency (and period dates on a named statement) are set exactly; rows are the
    new reading's; every payment of hers (date, amount, direction; amount-free undated lines ignored; an
    undated payment holds) must have its own counterpart, excluded ones as excluded. Extra payments counted
    on the item (summary.reread_carry.details.extra_rows) and pass normal readiness. Saved as System
    (queue_save.system_filled_only accepts the basis); her saver is kept on the carried record.
  - file-level work: per period of the new reading; released when her payments dated in it match, the
    printed account (last six) and currency agree with hers, and no period imported from her reading
    overlaps. Released periods listed per record in financial_review_details_release (recovery_state stops
    holding them); the rest stay held with per-period reasons in the carry log.
  - Her original records are never changed; carried_from names them (basis recorded).
- Measured (fresh readings, disposable SQLite, live inputs read only; scripts live26.py, measure_details.py,
  detailsjoin.py; private outputs details-export.json, measure-details-fresh.json, details-join.json):
  - plans for the 31 worked statement keys: settled 9, row-by-row carried 2, details 1, per-period 7 (all
    periods proven on 7 files); held: no_period_proven 3 (multi-currency files: the other account's period
    differs in currency; overlaps with an imported period), statement_ambiguous 3, work_in_another_batch 3,
    hand_added_rows 2, two_drafts 1. Per-period holds: currency_differs 4, overlaps_imported_period 3.
  - the 64: ready 8 -> 12 (all saved, all equal to truth); held: copy_of_saved 14, after re-read 17,
    own work not carried 5, sibling work not carried 3, duplicate_decision 6, investigator_decision 4,
    reader_not_affected 2, not_all_held 1. Lost 0.
  - the 50: ready 8 -> 12 (saved 12); held: copy_of_saved 12, after re-read 8, own work not carried 5,
    sibling work not carried 3, duplicate_decision 5, investigator_decision 4, not_all_held 1. Lost 0.
  - gains: 3 System-only statements (the 3 expected), 1 file-level details carry. 6 sibling-held targets are
    no longer held by her work; they stay held by normal readiness after the re-read (other named periods).
  - every saved period of the disposable run: 24 saved, 24 equal to truth, 0 differ, no truth period saved
    twice. No live writes (live session read-only at the database).
- Tests: targeted 19 files: 553 passed / 20 failed, the same 20 as base; recovery readers file 61 passed
  (11 new: details carry, payment mismatch, hand-added rows, row/statement notes, undated payment, rows changed
  between saves, System-only settle and its history guard, per-period release, end-to-end carry + System save,
  switch off).

## Unit C notes
# fin/aq-c-others: WIP notes (unit C, BNB2 waiting queue)

These notes hold counts and opaque document ids (sha prefixes) only. Real values and transcriptions are kept
under /mnt/owl-data/fin-real/aqc (mode 700).

## Scope

There are 72 targets: 56 are outside the truth corpus and 16 are in truth but held by the bench. The Santander
Consulta and Intercam/Kapital brokerage layouts belong to unit A, and the pipeline/re-read path to unit B.

## Measured on real bytes (mini corpus of 65 docs, base f2a52eae vs branch, readings reused)

The ready count went from 13 to 22 of 72. Wrong admissions were 0 in both runs, and critical-field errors were
0. No target and no admitted period was lost. The scored set has truth for 30 files: 17 tier-A, plus 13
t-visual transcriptions written for this unit and compiled VERIFIED.

| family (as resolved) | targets | ready before | ready after | what changed / why held |
|---|---|---|---|---|
| Monex (2022+ sideways, 2021 portrait) | 15 | 2 | 9 | profile names the 4 balance columns and the guarantee column |
| BBVA | 17 | 4 | 6 | OCR stroke between day and month (q51, q52). Held: 3 scans missing printed pages, 6 fund statements (not ledgers), q43 (OCR '141/JUL' day), q44 (currency) |
| Santander (B) | 21 | 5 | 5 | not reached in this unit |
| other (C) | 14 | 1 | 1 | Held: 9 BBVA scans missing printed pages (q61-q69), 2 brokerage currency (unit A), q38 balance, q58 |
| Kapital / Intercam | 4 | 1 | 1 | MXN sections not reconciled (amount columns) |
| Scotia | 1 | 0 | 0 | not reached |

The newly ready targets are q23, q24, q29, q30, q31, q35 and q39 (Monex), and q51 and q52 (BBVA). Every one is
scored against truth: the visual transcriptions cover docs dcefebd5, d89be099, deb1e564, d51c9120, d497c025,
d7849892, d4e0e81b, daf7e54f and d6b93449. The transcriptions of d5097dee, d4cc6be4, d4cb7388 and d532fd63 are
also VERIFIED and score their held sections.

Monex targets still held:

- q32 and q48 (EUR section, blank currency). The OCR reads the summary's opening label with a stray word, so
  the section splits after the currency heading.
- q33 and q27 (balance/reading).
- q45 and q46 (balance/reading).

## Engine: outline reading on sideways pages

Outline (vector glyph) reading previously ran only at rotation 0. Pages now OCR'd at 90, 180 or 270 read their
outlines in the turned frame (TurnedPage). The switch is TURNED_PAGES in vector_glyph_reading.py.

Across 21 truth docs with turned vector pages, the content changed in 17. Bench results on the 35 truth periods
from those docs:

- Product: base 28, branch 29, r14s-whole 28. Lost 0; gained df191ae7#1.
- Generic-only: the same, against r14s-whole-go. Lost 0.
- Wrong admissions: 0 in both modes.

On the aqc mini, new readings for the 8 sideways Monex docs changed nothing in the outcome.

## Regression

The Monex profile was checked by catalog equivalence on 87 truth docs, comparing base and branch in product and
generic-only modes. Ignoring routing seconds and layout fingerprint, the material catalog changes are:

- Product: df191ae7 (now proved), plus d23eb18d and dc0eacc0 (engine now agrees with library; served unchanged).
- Generic-only: those 3 docs.

The date-stroke rule's tokens occur in none of the 815 truth readings, so the truth catalog is unchanged by
construction.

## Tests

- New backend tests: DateSlashStrokeTests, and the Monex profile column roles.
- New engine tests: tests/test_turned_page.py, and the sideways glyph test in test_vector_glyph_reading.py.

## Gates (measured)

- Synthetic benchmark (branch): 0 wrong admissions; held 10/10.
- aqc mini, product and generic-only: 0 wrong admissions; 0 lost; generic-only ready 13 -> 22.
- Truth runs on 21 turned-page docs and 3 Monex docs: no period lost against r14s-whole or r14s-whole-go.
- Backend: 423 targeted tests pass. The wider financial suite shows the same 22 failures on base f2a52eae and on
  the branch (recovery/scheduler/re-read environment tests).
- Engine container: 117 passed and 50 skipped (the skips need a font). On the host, the font-dependent glyph
  tests (56) pass.

## Reader gaps: Santander (fin/rg-santander)
31 held BNB2 Santander statements (balance 16, reading 5, currency 5, no_activity 3, account 1, holder 1).

### Changes (statement_import_santander.py, santander_integral.py; each default on, fails closed)
- `LOUPE_FINANCIAL_SANTANDER_RULE_APOSTROPHE`: an apostrophe OCR'd for the column rule no longer breaks the heading (2 statements).
- `LOUPE_FINANCIAL_SANTANDER_COVER_SPACED_ACCOUNT`: the cover's account number split by OCR spaces still names the section (exact digits only; 1 statement).
- `LOUPE_FINANCIAL_SANTANDER_QUIET_COVER_CLOSING`: a section with no movements and zero printed totals takes its closing from the cover (equals opening) and passes the no-activity check (1 statement; it reconciles, held on saved work).
- `LOUPE_FINANCIAL_SANTANDER_BALANCE_STEP_AMOUNT`: an amount with a misread separator is read only when the running balance steps by exactly it, in its column's direction, right after a clean line (1 statement; it reconciles, held on saved work).
- `LOUPE_FINANCIAL_SANTANDER_INTEGRAL_RECOVERY` (new santander_integral.py): the older scanned ESTADO DE CUENTA INTEGRAL cheque section the general reader holds is proved from its printed running balance (unique amount/balance split per line, both ends agree with balances printed elsewhere, dates in period and in order, folio present, column agrees with direction). Shared code: one hook in statement_engine.propose_engine_statement, called only for a held engine statement, refused when another engine statement shares its pages (2 statements read; 1 ready, 1 held on saved work).
- A positionless-table rule was tried and withdrawn: it made a second account section of a shared-page file ready, and the saved sibling's table overlap then matched it as already imported (2 wrong admissions on the truth set). That identity overlap (statement_import._existing_statement, table-address overlap when the Santander reader gives no section rows) is shared code, not changed.

### Live (read only, fresh reading x branch)
4 of 31 ready or importable (was 0). Reconciling but held by an earlier reading's saved review work: 10. Stale statement keys with saved work: 3. Account carry conflict: 1. Overlap-trim domain: 1. Currency not printed (autofill proposal exists): 4. Integral scans with OCR-garbled amounts: 2. Integral period with an engine fragment on the same page (guard refuses): 1 file. Engine splits the period and loses the account: 1 file. Positionless continuation tables (needs a new reading or text-layer reconstruction): 2.

### Truth set (Santander corpus: 121 files, 178 periods; base 68d95b20 vs branch, readings reused, concurrency 1)
- Bench readings: clean ready periods 145 -> 146; per-period lost 0; wrongly admitted 0; critical-field errors 0; valid-looking wrong values 0.
- Live readings: clean ready periods 113 -> 122; per-period lost 0; wrongly admitted 0; critical-field errors 0; valid-looking wrong values 0.
- Both base and branch report the same 2 exact copies offered instead of set aside (pre-existing, not from this branch).

### Tests
test_financial_santander_integral, test_financial_statement_import_santander, _santander_query, _santander_subaccounts, _mexico_no_activity, _statement_import_kapital, _statement_engine: 320 passed.
