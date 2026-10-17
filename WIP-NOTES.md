# r8-import-ops — WIP notes (counts and opaque ids only)

Neil's directive unit, continuation of r7-import-ops (items 3 and 7 were unfinished). Branch `fin/r8-import-ops`
from `fin/release-1` d5985a0a. **Not pushed, nothing deployed, no live write** (every live access was a READ ONLY
transaction). Private detail: `/mnt/owl-data/fin-real/tmp/r8io/` (probes, comparisons, logs), benchmark runs
`/mnt/owl-data/fin-real/bench/r8io-base`, `r8io-final`, synthetic `/mnt/owl-data/fin-wt/bench-runs/r8-import-ops-86e2bf9b`.

## 0. Base: live commits carried by cherry-pick (`-x`), live -> here

| live | here | note |
|---|---|---|
| 511fe673 | 142ec48f | truth reader (Navy Federal) |
| 73622c7a | 6089ac83 | conflicts in statement_engine(.py, _profiles, tests) resolved keeping both sides (wave 6/7 rules and r-subpoena's); `_numbering_complete(..., after=None)` kept, payment-box skip and E4 `consumed` skip both kept |
| 7795610f | 4418b96f | |
| 33fd312c | 729adace | |
| 651dc9dc, f9d6105c, c50ce8e7, 169e4d4a | b9b5c9a0, 144b5d81, 85a34ee3, f0f5e043 | clean |
| fcb78072 | b43a4c07 | r7-import-ops' cached `_account_identity` now takes the credit-line kind; a test patched the plain-dict reading cache, now the two OrderedDict caches |
| 208e010d, 29426847 | e028b2c3, 32f02d48 | clean |
| 6573a90f | c08da758 | **message and new test file carried real identifiers (holder names, account numbers): replaced by invented values of the same shape here** |
| 7ad0e79a | 8a9b9a3b | **message named a real file: replaced by a description** |
| cbc9d356, 21a7da00 | 3efb3b19, d1b5dafa | test conflict: both tests kept |
| c0168f1c | 7ceaf224 | per-row digest cache merged with r7's narrowed fingerprint (`source_ids`/`periods`) in both paths |
| 61391b04, f73c6963, a16129cb | e22c58ef, a9db6d27, 80cf18e7 | clean |
| 06790ca4 | d60837e4 | **one rule per failed file** (below) |
| b247f3ba | 086b323a | read-afresh offered for files still counted as couldn't read |
| 0600e3f7 | ad3a02c0 | named-statement skip before the "being prepared again" bucket |
| e47c25c5 | — | skipped: its frontend is already here (r7-alex-queue); only its docker-compose hunk remained (deploy config) |
| b81f1712 | — | not carried (r-subpoena's WIP notes) |

Rule choice (06790ca4 vs r7-alex-queue): r7-alex-queue's `_failed_files` set-aside (removed / gone / copy, one
sentence each, counted apart from "Couldn't read") stays the one rule for files that could not be prepared;
06790ca4's statement-level rule is kept (an unreadable statement whose bytes another upload read moves to Copies,
`copy_reason` same_file_read); its second failed-file list (`copy_files`) and panel block are dropped so a failed
file is never listed twice. Reverse: restore 06790ca4's `failed` branch in `_set_aside_read_copies`.

Trial merge of the live branch onto this head (git merge-tree, read only): 15 files still report conflicts, all
where a cherry-pick was resolved here (textually different, same changes). Every live commit except b81f1712 and
e47c25c5's docker-compose hunk is on this branch: at the reunion these files take this branch's side.

**Base proof** (`bench/r8io-base`, code ad3a02c0 = all carried commits, frozen copy, `--readings bench/wave7`,
product default auto-save ON, concurrency 2): **1,147 / 1,343 ready, 0 wrong**, 0 critical-field errors (17,948
rows / 1,157 periods), held 4/4, copies held 148/153, **0 copies saved** (exit 0), 1,147/1,147 saved by the system.
Per period against bench/wave7: **0 lost, 0 gained, 0 held periods with changed reasons**. What r-subpoena's
rules change by family on the truth set: nothing in any family (the Navy Federal file is not in the truth set).

## Landed (this unit's own commits)

| item | commit | change |
|---|---|---|
| 7 (1) | b79e5680 | engine E10: an amount merged into its balance's cell takes the one signed amount column, proved only by the printed running balance; B7: a zero-only line (voucher `TOTAL $0.00`) may stand inside a quiet section |
| 7 (2) | 2c5f8544 | engine C5 `principal_only_balance` (reason only, never proves); hold reason carried on the row problem; batch reason `principal_only`; queue sentence "The statement prints only the principal balance; the opening amount owed is not printed on page N", ranked ahead of fillable details |
| 4 | 8287dad5 | harness `drain_readiness`: runs the service's readiness sweep until nothing is pending or a round removes nothing, before scoring |
| 3 | 86e2bf9b | `row_versions.RowValues`: values read from large JSON metadata reused per PostgreSQL row version (xmin); used by `_existing_statement`, `_admitted_sources`, `recovery_catalog`, and the comparison's pending items (scalar summary keys only) |
| fix | 9613d97c | review_carry and row_versions exported (package-surface test) |

## Navy Federal (truth id dfc15d7fbdc2c, live file 6e611846) — items 7(1) and 7(2)

Live stored reading copied read only, routed with this code in a scratch database:
- before (base): 203 / 205 verified periods proved, all equal to truth; held 14 (12 truth-unverified credit lines, 2 verified)
- after: **205 / 205 proved, all equal to truth (movements, opening, closing, dates, holder, currency); held 14 -> 12**
- the 12 held: all truth-unverified principal-only credit lines; prepared summaries: 205 ready, 12 attention, **all
  12 lead with the exact principal-only sentence and their page**. 0 proved period disagrees with truth.

## Item 3 — per-import cost (live case 49494305, READ ONLY probe, warm, a different period each round)

| step | base ad3a02c0 (load 10-11) | this head (load 10-11) |
|---|---|---|
| read path of one import (accept read, writer read, existing check, case comparison, own readiness) | **11.5-13.5 s** | **2.3-3.7 s** |
| existing-statement check | 1.9-3.9 s | 0.04-0.1 s |
| case comparison | 1.2-3.1 s | 0.8-1.0 s |
| one period read | 3.0-4.8 s | 0.5-0.8 s (up to 2.2 s for a period first read in the process) |
| own readiness inputs | 1.3-6 s | 0.08-0.2 s |

**Is < 3 s warm reached? Not shown.** The read path alone is 2.3-3.7 s at load ~10.5; the writes of an import (a
live write) were not measured, so the full import time is not known. The catalogue backfill (r7 decision 1, live
write) is still not run; the row-version reuse makes warm reads independent of it, cold reads are not.
Synthetic harness (`statement_import_cost.py`, 217 periods, SQLite, load ~9): one import 1.2-2.4 s, sweep
0.15-0.44 s; SQLite has no row versions, so it cannot show this change (it exercises the fallback path).

## Item 4 — readiness refresh before scoring

Final run: **35 statements pending -> 0 in 14 rounds (812 s)** before scoring (the 35 = andrews 26, intercam 3,
kapital 3, santander 2, monex 1, the same as integrate-7). **No period's outcome changed**: in each the
readiness_update reason left and every other reason stayed. Live queue: confirmed in code — the batch worker runs
`refresh_stale_readiness` every READINESS_SWEEP_SECONDS (60 s), the queue puts such statements under "Being
rechecked" and re-polls by itself while anything is moving. No click.
Finding (not fixed): automatic save fires only at the end of a file's preparation; a statement that becomes ready
later through this sweep stays ready in the queue until "Save all ready". 0 such periods in this run.

## Final whole set (`bench/r8io-final`, code 9613d97c, frozen copy, same 668 documents, `--readings bench/wave7`)

**1,147 / 1,343 ready (85.4%), 0 wrong**, 0 critical-field errors (17,948 rows), held 4/4, copies held 148/153,
**0 copies saved**, exit 0, 1,147/1,147 saved by the system. Against base and wave 7: **0 lost, 0 gained**.
Run on a private corpus (current manifest filtered to the 668 documents with stored readings): the shared truth
manifest gained 35 documents (66 periods) at 15:56 while this unit ran (the parallel truth unit); they have no
stored reading, so they are not in either run. Base rescored on the same manifest: identical figures.

Synthetic (`bench-runs/r8-import-ops-86e2bf9b`, code 86e2bf9b, `--readings bench-runs/real-wave7` because the
change is backend-only, product default): **105 / 125, 0 wrong**, 0 critical, holds 10/10, copy 1/1, 105/105 saved
by the system, exit 0; readiness refresh 4 -> 0 in 1 round.

## Tests actually run

- Full financial suite (CLAUDE.md command, live .venv, CHROMADB_PORT=1 CHROMA_PORT=1) on 86e2bf9b: **Ran 6,414,
  failures=4, errors=2, skipped=20**: 2 export failures (fixed in 9613d97c; exports + extraction_release then
  12 OK), 2 known unassigned_statement, 2 extraction_release subprocess timeouts under load (OK alone).
- Targeted: engine 154 OK (4 new tests, each failing on the previous engine), queue + batch summary 80 OK, import
  batches 105 OK, harness 13 OK, row_versions 3 OK, 36 affected modules 962 passed (5 recovery_followup /
  recovery_preparation failures under pytest are identical on the unchanged base).
- Frontend (as the app user, node_modules ownership restored, 0 root-owned files): tsc -b 0; vitest unit 304 files,
  2,127 / 2,129: the pre-existing route-check limit test and LedgerRowBrowser (96 s under load; 12/12 alone).

## Unverified

- Full live import time including writes (needs a live import).
- PostgreSQL row-version paths ran read only on the live database and on a stub session in tests; the SQLite
  suite exercises the fallback only.
- Browser vitest project not run.

## What is left of the seven items

Only item 3's end-to-end live target: the read path is measured, the full import is not. A next unit
(r9-import-ops) should measure one live import after deploy from the import timing log (or a scratch PostgreSQL
copy of the case), and, if it is above 3 s, profile the writer's writes. Items 1, 2, 4, 5, 6, 7 are complete.

## Decisions for Neil

1. **One rule per failed file** (r7-alex-queue's set-aside list kept, 06790ca4's file list dropped, its statement
   rule kept). Reverse in `review_queue._set_aside_read_copies`.
2. **Principal-only credit lines lead with their own sentence**, ahead of missing details. Reverse:
   `review_queue.REASON_ORDER`.
3. **Live branch history holds real identifiers** (6573a90f's test file and message, 7ad0e79a's message). They are
   redacted on this branch; a merge of the live branch into fin/release-1 would bring them back. Recommend the
   reunion takes this branch's side for those files.
4. Carried from r7: run the catalogue backfill live (dry run default); the row-version reuse no longer depends on it
   for warm imports.
