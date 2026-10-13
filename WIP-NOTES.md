# fin/s-inference: proposals for missing currency, bank, holder and account number (2026-10-13)

Base af76b2ac. Not pushed, not merged. Opaque ids only; private detail and the replay scripts are in
/mnt/owl-data/fin-real/alex/s-inference/ (replay.py, loo.py, live.py, *.json).

## Commits
- a763bf70 backend: `services/financial/field_proposals.py` (read-only proposals + `apply_confirmed_proposals`),
  review queue integration (entries carry `proposals`; new bucket `filled`, "Details filled automatically N"),
  statement-details listing carries `proposals` per unimported statement, `BulkEdit.basis` (why the values were
  chosen, kept in each file's account-detail history). Tests: test_financial_field_proposals (22), one save test in
  test_bulk_statement_details.
- cdd20f69 `backend/scripts/financial_apply_field_proposals.py`: dry run by default (read-only connection), `--apply`
  saves CONFIRMED proposals through the existing details save with actor System. The retroactive path; never runs
  by itself.
- deb43313 frontend: group details dialog ("Resolve N together", `BulkStatementDetails`) prefills the proposed value
  when a field is ticked, shows its source, "Use X" when the field holds something else.

## The rules (as built)
Currency: (a) printed on the statement is already adopted by the reader (a statement asking for its currency has
none), so nothing new is proposed from the page. (b) same account's saved statements, all agreeing (each statement's
period currency and the account record's currency). AUTO-CONFIRMED only with >= 2 such statements, the account
matched exactly and uniquely on two independent fields (account number + bank or holder), and no saved statement of
that account on overlapping dates (several currency sections share one account number at some banks). (c) the case's
usual currency (most common among saved statements), label "USD — the case's usual currency (175 of 175 saved
statements)"; never auto-confirmed.
Bank / holder / full account number: from the one known account the statement matches (full number, or the visible
digits of a masked number; plus bank/holder where both print them). Every saved statement of that account must give
the same value. AUTO-CONFIRMED only with two exact independent fields; a holder additionally only when saved
statements of the account exist both before and after the period. A full number is proposed only for a masked one.
Account identity = number at one bank: two full numbers sharing the visible digits, or masked + full records, are
ambiguous (nothing proposed); a holder never narrows the choice. Printed values are never replaced.
Switches: `LOUPE_FINANCIAL_CURRENCY_PROPOSALS`, `LOUPE_FINANCIAL_DETAIL_PROPOSALS` (both ON by default; reads only).
Layout-fingerprint matching (brief item 2, second form) is NOT built: saved statements do not keep a fingerprint.

## Proof on verified truth (bench/wave5 = ef0877d6, stored readings, no re-run of the benchmark)
1. Held statements of the run (targeted replay over benchmark.db, per live case of origin): proposals 39 (currency 36,
   all case default; bank 2; holder 1); auto-confirmed 2 (bank), auto-confirmed WRONG 0. Truth periods held -> ready
   because of this: 0. (The 2 bank fills are on statements also held by balance + reading; the one holder-only period
   gets a one-click proposal because its account has a single saved statement, not one before and after.) Case-default
   currency proposals: 23 of 23 with truth correct. The 23 currency-blocked truth periods: Synchrony 16 (no saved
   statement of that card in the run), Santander/BBVA/Monex 7 (account never saved, or Monex: one number, four
   currencies -> correctly no auto-confirm).
2. Stress test, leave-one-out over every saved verified statement (1,118): each detail blanked in turn, proposal made
   from all OTHER saved statements of its live case, compared with truth:
   - currency auto-confirmed 655, wrong 0 (same-account proposals 667, all correct; case default 451, 327 correct)
   - bank auto-confirmed 808, wrong 0
   - holder auto-confirmed 716, wrong 0 (proposals 805, 804 correct)
   - full account number from a masked one ("****" + last 4) auto-confirmed 589, wrong 0
   With the bank and holder also blanked (account number alone = one field): 0 auto-confirmed, all proposals one-click.
   Narrowed during this unit until wrong = 0 (what was dropped):
   - holder from the account record -> per saved statement (69 wrong: holders printed under another name over time);
   - holder needs saved statements before AND after the period (1 wrong: an account printed under a new company name
     after all its saved statements); drops 89 auto-confirmations (805 -> 716 confirmed);
   - a holder no longer narrows the account choice (1 wrong: masked last digits shared by a paired account, the other
     excluded only by its holder); drops 169 masked-number confirmations.

## Live, read-only (af76b2ac data, 2026-10-13)
- 49494305: waiting 436 -> 436 (0 leave the queue). All 194 currency statements get the one-click proposal
  "USD — the case's usual currency (175 of 175 saved statements)"; none auto-confirms (186 come from one subpoena-
  response file with no account number, holder or bank on the statements). Re-read in USD (read-only): 0 of 194 would
  be ready; 185 then need account number + holder (+ bank) + balance + reading, 9 could not be re-read. So the
  "299 waiting only for currency" are not one decision away: currency is only the first question the reader asks.
- d5b330d1: waiting 156 -> 146; 10 move to "Details filled automatically" (currency, same account, 2-7 agreeing
  saved statements; all 10 agree with the currency code in their file names). Re-read with the filled currency:
  5 ready, 5 still held (reading 2, balance+reading 2, balance+no activity 1) and return to the queue with their real
  problem after the save. One-click proposals: currency 5 (same account, not confirmed), holder 11; 1 holder
  auto-confirmed on a statement with other problems. Dry-run save (CLI): 11 statements, 4 grouped changes, 0 errors.
- Other four cases: no waiting statements.
- Timing (probe process, cold, use_cache=False, flags off/on, two runs each): queue 49494305 8.3/9.9 s vs 9.6/8.8 s;
  d5b330d1 37.9/27.2 s vs 33.8/29.4 s (noise dominates). The proposal knowledge query costs 1.4-1.5 s cold, 7-19 ms
  warm (cached per case by a count/updated_at fingerprint); it runs only when a waiting statement lacks a detail. The
  statement-details listing gains the same query.

## Not done / for other units
- Nothing saves by itself. `filled` entries are listed in the queue response (`filled`) but no queue UI shows or saves
  them yet: s-queue-actions' save must call `field_proposals.apply_confirmed_proposals(session, case_id=..,
  entries=queue['filled'] (+ waiting entries with confirmed proposals), apply=True)` before saving ready statements
  (statements stay 'attention' in their batch until the values are saved). Its status line already counts them.
- BatchCurrencyEditor (batch "choose currency" dialog) and the single-statement currency control show no proposal;
  the queue sentence and the group dialog do.
- Not click-tested in a browser over the server IP.

## Tests run
- Backend (CHROMADB_PORT=1 CHROMA_PORT=1): field_proposals 22, review_queue + bulk_statement_details +
  statement_import_router 157 passed (with field_proposals); batch_review_summary + layout_memory + router 41 passed.
- Frontend (as conorbowles51): tsc -b clean; vitest BulkStatementDetails 8 passed; `npm run build` passed; no
  root-owned files in node_modules.

## Decisions for Neil
1. The currency premise: in 49494305 the 194 currency statements need much more after the currency (0 of 194 ready
   once read in USD). Worth a reader unit on that subpoena-response file (no account number/holder read on 186
   statements) before more field work.
2. Holder auto-confirm requires saved statements before and after the period (built; measured necessary). Keep?
3. Should "Details filled automatically" statements be saved without a click by the queue's auto-save (s-queue-actions),
   or wait for "Save ready"? Today: nothing saves them until the queue save or the CLI runs.
4. Case default for (c): most common currency among saved statements. Alternative: none when the case holds several
   currencies (d5b330d1: 313 saved in MXN/USD/EUR; in the leave-one-out 327 of 451 case-default proposals were right).
