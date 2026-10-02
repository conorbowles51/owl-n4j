# U0 frontend triage — WIP notes (2026-10-02)

## Done
- Root cause 1 (StatementImportPanel.test.tsx, stale test): commit 1bd69ab2 deliberately moved
  standalone import from POST `/confirm` to POST `/queue-import` (returns `{operation}`), with the
  receipt read back via POST `/confirm-result` (`{receipt, operation}`). Test mocks still answered
  `/confirm?`, so the component fell into its receipt-polling loop (0,1,2,4,8,8 s) and tests timed
  out or never called onImported. Updated the base mock + overrides (`queued()` / `importCall()`
  helpers); failure path now throws `ApiError(..., 409)` like the server would.
  Result: SIP file 31-41 failed -> 2-3 failed (67 tests).

## Remaining in StatementImportPanel.test.tsx
- "keeps manual rows ..." — times out at 5000 ms (takes ~7 s alone, no import call). Looks
  load/slowness only; check whether it passed pre-release on an idle box before raising timeout.
- "imports completed Merrick years ..." — PASSES alone (4.7 s), fails after "keeps manual rows"
  times out (leftover state / 5 s limit). Likely same slowness cause.

## Measurements
- Full `vitest --project unit` under heavy host load (load avg ~10, 6 cores, run in parallel with
  another vitest): 92 failed / 1960 passed, 29 files; 64 of the 92 were "Test timed out in 5000ms"
  -> most non-SIP failures are probably load-induced. Original U0 count was 72/1980 (17 files).
- Non-timeout failures outside SIP (to triage next, run each file alone on a quiet box):
  CandidateSourcePicker, FinancialAccounts, FinancialBatchPanel, PdfCandidatesPanel (2),
  ReferencedAccounts, StatementControlPicker, StatementEditorDraftPanel — all "Unable to find role"
  (findBy 1 s default; possibly load too).

## Next
1. Re-run each remaining failing file alone (FinancialPage 15-17, FinancialSourceAudit 4,
   LedgerRowBrowser 2, + singles) — separate timeouts from real assertion failures.
2. Frontend files touched by the release: BulkStatementDetails.tsx, BatchReviewSummary.tsx,
   FinancialBatchPanel.tsx, StatementImportPanel.tsx, lib/statement-import-recovery.ts.
3. Final `npx tsc -b` + full unit run; record counts.
