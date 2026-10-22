# fin/queue-ui — Review Queue UI fixes (Alex's live test call)

Branch `fin/queue-ui`, from live `6f626b2a`. Frontend: `frontend_v2/src/features/financial`. One backend commit (additive fields only, no admission change). Merges cleanly with `fin/live-backlog` (checked with `git merge-tree`).

Verification throughout: targeted vitest files plus `npx tsc -b` (clean). Not verified in a browser against the live app or live data. Each point below says what still needs checking live.

| # | Item | Commit |
|---|---|---|
| 2 | Batch edit ("Fix all N together") broken | 3e0a34a6 |
| 1 | Inline currency / bank / holder on the row | a0b82807 |
| 3 | Bulk confirm for "No payments read" | a3eca70d |
| 4 | Period + opening/closing balances on rows (backend) | 304fc5b3 |
| 4 | Period + opening/closing balances on rows (frontend) | f51feb7b |
| 5 | Truthful save counts | c006caa4 |
| 6 | Statement open speed | ed2af041 |
| 7 | Categories under Transactions | bb953b70 |
| — | Queue paging against the fin/live-backlog API | 9a9cde8c |

## 2. Batch edit broken — 3e0a34a6
**Cause** (reproduced in `ReviewQueueBulkFix.test.tsx`, which fails without the fix). The shared-fix editor's React key, draft key and listing query key were all built from the exact list of statements on screen. While files are being read or statements are rechecked, the queue polls every 15 s. So when one statement joined or left the list, the editor remounted under a new draft key. The dialog closed, her selection and value were lost, and the slow listing started again. On a live case that is always reading, a shared fix could not be finished.

**Fix.** `BulkStatementDetails` takes a stable `scopeName` (the issue plus the file filter) and filters its listing on screen from the latest selection. When it can list fewer statements than the queue chose, it says "Listed X of the Y statements". The shared-fix result now shows outside its box, so it still appears when the fix clears the list.

**Also fixed (a3eca70d).** The shared fix only appeared after choosing an issue filter. The filter buttons are hidden when only one kind of issue is waiting, so in that case there was no shared fix at all. The only listed issue now counts as chosen.

**Left.** A queue entry whose `statement_id` does not match a listed period could not be checked without live data. Example: a file-level currency question while the listing has period rows. Such an entry is now counted visibly as "Listed X of Y", not dropped silently. Check this on the live case.

## 1. Inline per-row editing — a0b82807
The removed control is `466b7585` in `FinancialBatchPanel.tsx`. It is the "Choose printed currency" select on each attention statement, still present in the batch list. The queue replaced that list as the work list, and the queue never had the control.

The new `QueueRowDetails` puts a currency select, a bank field and an account-holder field on the row. They are pre-filled with the current value or the queue's proposal. Rows missing one of these fields open with the fields shown; other rows show "Change currency, bank or holder here". No dialog opens. "Fix all N together" stays beside it.

**Save path.** It does not use the old per-file `/files/{source}/currency` endpoint. That endpoint re-prepares the whole file and refuses whenever the batch is busy or the file has saved corrections. The row uses the same account-details flow as the shared fix: list (for the revision), preview the changed fields only, then save that preview with the same request id. The server checks it exactly as it checks a shared value. If the preview changes nothing or finds a field that now reads differently, nothing is saved and the row says why. Afterwards the queue refreshes and says where the statement stands.

**Tests:** `QueueRowDetails.test.tsx`.

**Left.** Each row save lists that statement's file, which is one read on the server. Check the latency live.

## 3. "No payments read" bulk confirm — a3eca70d
`QueueNoActivityConfirm`:
- A checkbox on each row, plus Select all N, with an "X of N selected" count.
- An attestation checkbox.
- "Check which of the N can be confirmed" previews the selection through the existing per-statement no-activity confirmation (account-details `no_activity_confirmed`). This is the same path as the dialog and the statement. Listings are chunked by 50 files and previews by 200 statements.
- It shows "N of M will be confirmed, K cannot be: reasons", with every excluded statement listed. Nothing is saved before that.
- Confirm saves exactly that preview. The result then says how many are still waiting and how many are ready.

The server decides each statement's eligibility; no admission rule changed. No new backend endpoint was needed.

**Tests:** `QueueNoActivityConfirm.test.tsx`.

**Left.** The time to list many files at once on the live case.

## 4. Opening/closing balance and period on each row — 304fc5b3 (backend), f51feb7b (frontend)
**Backend (additive).** `review_queue._entry` now also returns these fields, copied from the stored batch summary:
- `opening_minor` and `closing_minor`, taken from the `closing_balance` check
- `balance_status`
- `transaction_count`

Nothing is read again. Test: `backend/tests/test_financial_review_queue_balances.py` (2 passed, with the deploy venv's pytest). The queue's in-memory entry cache is per process, so the fields appear after the restart.

**Frontend.** Each row has a line "period · opening X CUR · closing Y CUR · N payments read · balances add up/do not add up". A balance that was not read shows "not read", never 0. Without a currency, the amount is shown in minor units and says so. Tests: `lib/review-queue-balances.test.ts` and `ReviewQueuePanel.test.tsx`.

## 5. Truthful counts — c006caa4
**Cause.** "Import 5 ready" counted ready statements and statements with details filled automatically together. A filled statement is sent only if filling makes it ready. The ones it did not make ready were never sent and never mentioned. Held copies without a filename were also filtered out silently.

**Fix.**
- **Button.** It now reads "Import 1 ready, and 4 once their details are filled".
- **Result.** "Of 5 counted as ready: 1 imported, 1 held: reasons, N still importing, 3 not imported: details filled, but they still need something". Any statement the server has not reported on is counted as "not reported yet", so the parts always add up.
- **Lists.** The statements that were not ready are listed with what each still needs, from the refreshed queue. The held list counts nameless entries instead of dropping them.

The backend agent's notes explain the other half of "5 ready, 1 imported": stored readiness differs from today's admission, and its backlog sweep now refreshes the stored readiness.

**Tests:** `ReviewQueuePanel.test.tsx`.

## 6. Opening a statement is slow — ed2af041
This profile comes from reading the code. It was not measured on the live app.

**What opening a statement fetched, in order:**
1. `GET /batches/{b}/items/{i}`. This runs `checked_batch_items(reading='targets')`, so it may read the statement again.
2. Only after that, the review mounted and asked for `GET /statement-import/{file}?currency&statement_id`, a second read of the same statement.
3. Then the checks and coverage POSTs, which need that reading.

Steps 1 and 2 ran one after the other. Closing the statement then fetched the whole case queue again, a request of up to 60 s, even when nothing had changed. `include_positions` is not on this path; it is only in the saved-record position editor, which already loads it on demand.

**Fix.**
- The shared `statementReadingQuery` is started from the queue entry together with the batch item. It stays fresh for 10 s so the review uses it instead of reading again. If the entry's currency or statement id differs from the item's, this falls back to the old fetch.
- Back to the queue no longer reloads it. Every save inside the statement already refreshes the queue, and the queue polls by itself.
- Paging (below) also limits the list to 50 rows.

**Tests:** `ReviewQueuePanel.test.tsx` checks that the reading is requested while the item is still loading, and that closing does not fetch the queue.

**Left.**
- Measure the time to open a statement on the live app (devtools network panel).
- The two server reads of the statement are still two reads, now in parallel. Making them one is a backend change: the item response could carry the reading, or the reading could be cached across the two requests.

## 7. Categories — bb953b70
The Category dropdown is removed from the Financial page header (Overview, People & businesses, Follow money, Trends, Payment graph). Categories are chosen and managed in the Transactions tab's payment table, which already had the filter and the category manager. A category chosen there still narrows the analysis views. Those views now say "Showing category: X" with "Change under Transactions" and "Show all categories", and show nothing when no category is chosen.

**Tests:** `ActiveCategoryNotice.test.tsx`.

## Paging — 9a9cde8c
Built against the contract in `fin-wt/live-backlog/WIP-NOTES.md` (head `7b80755d`): `limit`, `offset`, `page_list`, `issue` and `fresh`, plus the response fields `totals`, `page`, `issue_counts`, `ready_item_ids` and `refreshing`.

- **List.** The list shows 50 per page, with "Showing a–b of N" and Previous/Next. Issue counts come from `issue_counts`, and the issue filter is applied by the server.
- **Freshness.** Saves and fixes refetch with `fresh=1`. While `refreshing` is true, the queue says so and polls.
- **Actions that cover everything, not just the page:**
  - Import reads the whole queue and uses `ready_item_ids`.
  - The shared fix and the no-payments confirm read every statement of the issue (limit 5000; the dialog says when it is capped).
  - Check again and Read afresh read the whole queue.
  - A link to a statement that is not on the current page finds it in the whole queue.
- **Older backend.** Against a backend without paging, the full lists are paged on screen.

**Tests:** `ReviewQueuePaging.test.tsx`.

**Left.**
- Next and Previous inside a statement move within the current page. At the end of a page they go back to the list instead of loading the next page.
- "Statement X of N" counts the page.
- The list is paged, not virtualised. At 50 rows virtualisation is not needed.
