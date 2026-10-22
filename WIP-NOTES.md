# fin/live-backlog — work in progress

## Review queue API contract (for the frontend_v2 work)

`GET /api/financial/statement-import/review/queue`

Parameters (all new ones optional; without them the response is exactly as before, every list complete):

| param | meaning |
|---|---|
| `case_id` | as before |
| `file_id` (repeatable) | as before: limit to these files |
| `limit` | cap on every entry list (`items`, `ready`, `filled`, `reader_fix`, `rechecking`, `copies`, `unreadable`). `0` = counts only. Omitted = no cap. |
| `offset` | start of the page in `page_list` (default 0). Other lists always start at 0. |
| `page_list` | which list `offset`/`issue` apply to: `waiting` (default, the `items` field), `ready`, `filled`, `reader_fix`, `rechecking`, `copies`, `unreadable` |
| `issue` | only entries of `page_list` whose `issue_reason` is this key (e.g. `currency`) |
| `fresh` | `1` = wait for a queue built from the current data (use it for the refetch right after a save or fix). `0` = a queue built moments ago may be returned at once while a new one is built in the background (`refreshing: true`). Default: `0` when `limit` is given, `1` when it is not (the views that predate paging keep their behaviour). |

Response: every existing field, plus

```jsonc
{
  "totals":  {"waiting": 612, "ready": 3, "filled": 0, "reader_fix": 40, "rechecking": 113, "copies": 9, "unreadable": 4},
  "page":    {"list": "waiting", "issue": null, "offset": 0, "limit": 100, "returned": 100, "total": 612},
  "issue_counts": {"currency": 300, "reading": 250, "balance": 62},   // over every waiting entry (file filter applied)
  "ready_item_ids": ["..."],      // every ready entry's id, never truncated (for "Import N ready")
  "refreshing": false,            // true: this answer predates the latest change; a fresh one is being built
  "as_of": "2026-10-22T21:00:00+00:00"  // when this queue was built
}
```

* `totals[list]` is the full length of that list (file filter applied, issue filter not); `page.total` is the length after the issue filter. Show "showing `returned` of `total`" whenever `returned < total`.
* `counts` and `status_line` are always whole-case (or whole-filter) numbers, never page numbers.
* While `refreshing` is true, poll again (the existing 15 s poll is enough) and say the numbers are being updated.

`GET /api/financial/statement-import/review/status?case_id=` (counts only): `counts`, `status_line`, `reading`, `refreshing`, `as_of`. It never waits for a rebuild when a queue for the case was built before; use it for badges and the cross-case view instead of the full queue.

`POST /review/save` and `/review/fill` are unchanged.

## What changed (branch fin/live-backlog, from live 6f626b2a)

### A. Re-read held statements after every engine release (`recovery_campaigns`, `recovery_readers`, `deployment_recovery`)
* Root cause: the reader campaign's release id was fixed (`statement-recovery-2026-10-02-readers-v1`) and runs are unique per (case, release), so it ran once (17 Oct) and never again; "affected" was a hand-kept digest list.
* Now `reader_campaign()` names its release `statement-recovery-engine-<first 32 hex of the deployed pdf_extraction.py sha256>` (read from `evidence-engine/app/pipeline/pdf_extraction.py` beside the backend, the file the engine image is built from). A reading is affected when its recorded `pdf_extraction.py` digest differs from that. Unchanged code = same release = no new run; a new engine = one new run per case. A reading with no valid processing record is still never selected (`unrecorded_reader`); the old digest list is kept only as history (it cannot help a reading that recorded no digest).
* An earlier engine release's statements not yet handed to a batch move to the newer release (`kept`, `newer_release`); ones already handed off are followed to the end by their own run.
* Several batches (Erica Hopper: 476 of 487 batch files): an original held in several batches is now one selection. Every batch file must qualify on its own (no edit/draft, decision, duplicate decision, saved/pending import, ready period on any reading of it in any batch); a member whose periods were all retired already is skipped; a batch made after the cutoff, or one that takes the original after scheduling, leaves it. Each batch gets the same attempt id per earlier reading, so `create_statement_version` makes one new version and the engine reads it once; every batch prepares its reviews from it through its own retry path.
* Bounded and ingestion-safe: at most `LOUPE_FINANCIAL_READER_RECOVERY_AT_ONCE` (default 4) hand-offs in flight host-wide; no new hand-off while other evidence files are `processing` (count reused 30 s). The worker now looks at 8 recovery items per 10 s turn (was 2) so waiting items rotate.
* Queue: a held statement scheduled for a re-read (pending, waiting for a slot, or being read) counts under "Being rechecked N" (live, not cached); a batch file handed back (`waiting` + `recovery`) counts as rechecking too.
* Switch: `LOUPE_FINANCIAL_READER_RECOVERY=0` turns the campaign off (default ON; live already has it `=1`).

### B. Ready backlog saves itself (`queue_save.sweep_backlog`)
* Runs in the batch worker's readiness round (every `READINESS_SWEEP_SECONDS`), at most 30 statements / 20 s per round: stored `ready`, no stored check, no edit or draft (`backlog_choice`), then `save_statements(only_reconciled=True)` as System in chunks of 10 (`save_backlog`). `scripts/financial_save_ready_backlog.py` now calls the same two functions.
* When today's admission holds a statement whose stored state says ready (reason "No longer ready…", "Being rechecked…" or a describe sentence), its stored readiness is refreshed (`refresh_readiness`), so the queue stops calling it ready and the counts agree with what a save does. Held statements are not retried until their row changes.
* Switches: `FINANCIAL_AUTO_SAVE_BACKLOG=0` stops only this sweep; `FINANCIAL_AUTO_SAVE_READY=0` stops every automatic save.

### C. Review queue (backend only; the UI is another branch's work)
* Cache: per case, keyed by the register fingerprint, at most 8 cases and 40,000 entries in all (LRU); cached views are never mutated and never deep-copied (a response copies only what it returns). The failed/set-aside/copy-file checks are part of the cached view.
* One build per case at a time per process (others wait for it). A paged read or `fresh=0` answers from the previous view at once (`refreshing: true`) and rebuilds in a background thread; `/review/status` does too (counts only).
* Paging: see the contract above. Unpaged reads behave exactly as before.
* Worker turns: batches holding pending imports get the first turns (`import_batches.turn_batches`), so a save no longer waits behind up to 100 batches reading files.

## Measured queue timing (synthetic case, SQLite, PostgreSQL fingerprint simulated)

`tests/financial_large_queue.py` builds N files x 4 statements from one really prepared statement (60 % waiting, 30 % ready, 10 % nothing read). Seconds for one GET-equivalent call (`case_review_queue` + JSON encoding), niced, on the live host:

| case | before (6f626b2a) | after |
|---|---|---|
| 1,000 statements, first open (cold build) | 1.05 | 0.58–0.84 (build unchanged) |
| 1,000, unchanged, whole queue | 0.06 (deep copy) | 0.014–0.037 |
| 1,000, unchanged, page of 100 / counts only | n/a | 0.010–0.024 / 0.005–0.011 |
| 1,000, after any change, poll | 1.09 (full rebuild, blocking) | paged: 0.021–0.034 (previous view, `refreshing`), rebuilt in background |
| 3,000 statements, first open | 3.05 | 3.1 |
| 3,000, unchanged, whole / page of 100 / counts | 0.21 / n/a / n/a | 0.076 / 0.026 / 0.024 |
| 3,000, after any change, poll | 4.69 (blocking) | paged: 0.04 |
| response size, 3,000: whole / page of 100 / counts | 2.16 MB | 2.19 MB / 0.25 MB / 0.04 MB |

Synthetic stored summaries are small and SQLite has no coverage records, so the absolute build is far below live (~1 min on BNB2-size cases). The structural win carries over: on live the build now runs at most once per case and process per change, in the background for paged reads and `/review/status`, instead of in front of every poll of every open tab. Only the very first open of a case after a backend restart still waits for a build (prewarm keeps recently opened cases warm afterwards). Re-run from `backend/`: `python3 scripts/financial_review_queue_timing.py 250` (1,000 statements) or `750`; it uses only the test fixture (SQLite), never a configured database.

## Live findings explained (code reading only)

* **Erica Hopper several_batches 476**: fixed by the several-batch selection above.
* **BNB2 not_prepared 480** (batch file never reached `checked`): the classification cannot tell which of these it is, so the estimate script now prints `not_prepared` broken down as `batch status/file status[/auto][/recovery]`. From the code, the candidates are: (1) `error` files are terminal: only lock conflicts are retried (3x); an engine read that failed, a moved/removed source, or "a review decision was saved after Retry" stays an error until someone presses Retry (they show under "Couldn't read" files); (2) `waiting`/`processing` files of a **paused** batch never move (the pause is the investigator's); (3) files of a preparing **automatic** batch start at most `auto_read.IN_FLIGHT = 2` readings at a time per batch, so a 300-file automatic batch reads for hours; (4) a file waiting on `SHARED_PREPARATION_WAIT` follows the newest batch preparing the same reading; (5) an engine reading left `processing` (job lost) has no timeout here. Run `financial_reader_recovery_estimate.py --case <BNB2> --select-only` after deploy to see which; nothing was changed for (1)–(5) in this branch.
* **Erica Hopper 603 `ready` items but 6 backlog candidates**: the queue counts statements, not batch items. Items of a statement already imported or being saved through another batch (2,264 imported) are `imported` in the queue; copies are `copies`; only the newest batch's preparation stands for a statement; so most of the 603 rows are older-batch duplicates of saved statements and were never saveable (a save holds them "Already saved through another batch"). The queue's ready count was 6. "5 ready, 1 imported" is the stored-vs-today's-admission gap: the queue reads stored readiness; the save runs today's admission (`reading='all'`). The backlog sweep now refreshes the stored readiness of any statement admission holds as not ready, so the queue stops showing it as ready.
* **pending_import that stays pending**: imports only run in their batch's turn; turns went oldest-activity-first, 2 at a time, up to 30 s each. Now batches with pending imports go first. An import that fails records its error on the item (existing `_import_item` path), so it surfaces in the queue.

## After deploy

1. Nothing to migrate. `LOUPE_FINANCIAL_READER_RECOVERY` may stay `1` (default is on now); make sure `FINANCIAL_AUTO_SAVE_BACKLOG` is unset or `1`.
2. The engine image must be rebuilt from the same tree (deploy.sh does), or readings keep recording the old digest; the new run per case then still happens only once per release.
3. Restart the backend: the recovery worker snapshots every case for `statement-recovery-engine-<digest>` at start (one pass, read only except the run rows).
4. Watch: `financial_recovery_runs` per case for the new release, items moving `pending → waiting → reading → recovered/unchanged/review`; the queue's "Being rechecked N"; logs `Ready backlog:` and `Reader recovery scheduled`.
5. Read only checks: `python3 scripts/financial_reader_recovery_estimate.py --case <id> --select-only` (eligible / excluded / not_prepared breakdown), `python3 scripts/financial_save_ready_backlog.py --case <id> --check`.

## Left

* The cold build itself (first open per process) is unchanged; on live it is dominated by `checked_batch_items` over every representative and the fingerprint SQL (which hashes every transaction row of the case). A per-case persisted view would remove it.
* Automatic retry of `error` batch files and a timeout for engine readings stuck `processing` (not_prepared causes 1 and 5): needs the live breakdown first.
* `tests/test_financial_deployment_recovery.py`: 9 tests fail identically on 6f626b2a (DetachedInstanceError in the fixture); untouched.
* frontend_v2: no change on this branch (the UI agent builds against the contract above).
