# r-recovery: make the reader improvements reach statements already in Loupe

Branch `fin/r-recovery`, based on `fin/release-1` at `1c840355` (after the wave 3 merge). Headless session, 2026-10-02.
Nothing was pushed or merged. **The live dry run and the live audit were NOT run** (see "Not done" below).

## What the problem was

A deploy only changes the reader for new uploads. Statements already in a batch keep the reading they were given
when they were uploaded, which in the live 244-item batch was 23 Sept. The deployment recovery worker only runs
its three Sept 24–25 campaigns, so nothing re-reads those statements with today's engine.

## Landed

| commit | what |
|---|---|
| `e32cd7a1` | Reader recovery campaign `statement-recovery-2026-10-02-readers-v1` (`services/financial/recovery_readers.py`, registered in `recovery_campaigns.py`, wired into `deployment_recovery.py`). **Off by default**: the worker schedules it only when `LOUPE_FINANCIAL_READER_RECOVERY=1`. 18 tests. |
| `58c789e2` | Dry-run estimator `backend/scripts/financial_reader_recovery_estimate.py`. 4 tests. |
| `ff0d86f0` | Read-only admitted-ledger misread audit `backend/scripts/financial_ledger_misread_audit.py`, plus `benchmarks/statement_automation/recovery_simulation.py`. 4 tests. |
| `5296b6a6` | The simulation also runs the real campaign end to end and scores what it admits against the printed truth. |

### How the campaign works

* **Unit:** one file in one batch. It hands the file back to that batch's own durable "read again" path
  (`recovery.fresh_reading` on the batch entry, the same path Retry uses). The batch then makes a new version of
  the original (idempotent per attempt), reads it with the current engine, prepares fresh reviews, and retires
  only the earlier reading's unedited held periods (`superseded_reading`, kept in history). **The campaign never
  imports anything.** Admission still needs the ordinary readiness gates and an investigator's Import.
* **Selection is all-or-nothing per file.** A file qualifies only when all of the following hold:
  * every period is held (`attention`);
  * nothing on the file or its original carries investigator work. That means:
    * no saved edit (`review_request`) and no saved review progress;
    * no period that is imported, queued, skipped, ignored as a duplicate, removed or assigned;
    * no admitted source document;
    * no ignored or restored duplicate disposition, and no disposition a person recorded (automatic
      "not a duplicate / retained / needs comparison" projections do not count, because nearly every prepared
      period has one);
    * no removal of the file or its imports;
  * the original is in exactly one batch;
  * the file is not currently processing;
  * the reading's own engine record (`processing_manifest.source_files_sha256['pdf_extraction.py']`) is one of
    the **14 exact earlier digests** in `AFFECTED_EXTRACTION_SHA256`. These are every committed version from
    `7b0013fb` (10 Sept, when the record began) to `13d03dbe`. The current file (`7bd84c16`, digest `e6526e20…`)
    is excluded, so a new reading is never selected again. Unknown or unrecorded readers are never swept.

  Every exclusion is counted by reason in the snapshot's ingestion log.
* **Execution:** the rules are checked again under the case and batch locks before the hand-off. If anything
  changed, the item ends `kept` and nothing is touched. A paused batch stays paused (the item waits). Once the
  batch finishes, the item records `recovered` (some period is now ready) or `unchanged`, with period counts.
  Idempotent and resumable like the other campaigns (deterministic run, item and attempt ids).
* **Kill switch:** with the flag off, `next_recovery_items` stops dispatching this release's items. A started run
  simply pauses.

## Numbers

### Benchmark (fresh-upload track), required gate

`bench-runs/r-recovery-final` (code `ff0d86f0`, corpus v4, `OMP_THREAD_LIMIT=1`): **exit 0. 65/124 ready w/o edits
(52.4%), 65/107 recoverable (60.7%), 0 wrong admissions, 0 critical-field errors.** This is identical to the
merged baseline `release-1-w3`. That is expected, because nothing on the fresh-upload path changed.

### Simulation: a "live" case read by an older engine (synthetic corpus v4, 92 PDFs / 125 periods)

`python -m benchmarks.statement_automation.recovery_simulation --old-root <git archive of an old rev> --out DIR`.
The simulation reads the corpus with the OLD engine and prepares one batch with today's backend. It then:

1. runs Import all;
2. runs the estimator, the audit and the real campaign;
3. runs Import all again;
4. scores against the printed truth.

| old engine | admitted by Import all (wrong) | campaign scheduled files / held periods | periods ready after re-read | newly admitted | wrong among new |
|---|---|---|---|---|---|
| `60b6706a` (23 Sept, like the live batch) | 60 (4 wrong + Merrick-08) | 40 / 44 | **7** (Andrews 2, generic 3, Credit One 1, Merrick 1) | 7 | **0** |
| `bb3ccef3` (29 Sept, Andrews crop reread) | 68 (4 wrong + Merrick-08) | 37 / 40 | 3 (generic 3) | 3 | **0** |

* **Yield is modest:** 7 of the 44 held periods on the corpus. Most held periods there stay held for reasons a
  re-read cannot fix: balance 14, no activity 8, currency 6, holder 4, reading 13 (counts overlap). The dry-run
  estimator predicted 6 of 44 for the 23 Sept engine. It undercounts one because its scratch batch lacks the
  already-imported previous Merrick statement the derived start needs.
* **The synthetic corpus cannot predict the live yield.** The live Andrews batch's blocking profile (reading 170,
  balance 87) is the kind of problem the 29 Sept crop reread was built for. Only the live dry run will say.
* Run dirs: `bench-runs/r-recovery-sim-0923`, `bench-runs/r-recovery-sim-0929` (`summary.md`, `simulation.json`).

### Audit on the simulated ledgers

Both runs scored the same way:

* **The old engines' 5 wrong admissions were all flagged.** These are Credit One 6 and 7, Andrews 2021-05,
  generic-11 and Merrick-08. Merrick-08's truth period has an unprinted start, so the scorer listed it as
  "unmatched"; it is the corpus's compensating Merrick case.
* **"disagrees"** (the current reader confirms a different value) flagged 4 periods. All 4 are wrong admissions.
  There were no false alarms.
* **"disputed now" only** (the current reader will not confirm the digits) flagged 4–5 periods. 1 is wrong
  (Credit One 6) and 3–4 are correct periods on faint or 150 dpi scans.
* Native-text statements are skipped (29 of 68).

## Tests actually run

The live `.venv` python ran pytest with `CHROMADB_PORT=1 CHROMA_PORT=1`:

* New: `test_financial_recovery_readers` 18, `test_financial_reader_recovery_estimate` 4,
  `test_financial_ledger_misread_audit` 4. All pass.
* Adjacent suites, run together: recovery_campaigns, deployment_recovery, recovery_scheduler, recovery_followup,
  recovery_restored_scope, recovery_control_contention, exports, plus the 3 new files.
  * Result: **125 passed, 12 failed**.
  * The 12 are **pre-existing**: the identical 12 fail on a clean export of HEAD `1c840355` (99 passed, 12
    failed). They are 9 in deployment_recovery and 3 in recovery_followup, all
    `DetachedInstanceError` under pytest.
  * These are pytest-style function tests, so the unittest `discover` suite in CLAUDE.md never runs them. That
    is why the recorded baselines don't show them. Not investigated further.
* Full backend suite and frontend: not run. No frontend change. Backend changes are confined to the 3 recovery
  modules plus one export line.

## Not done / unverified

* **Live dry run and live ledger audit: NOT run.** The permission classifier blocked reading the service database
  configuration ("credential exploration"), and I did not try to work around it. Neil (or a session with that
  permission) runs, from `backend/` with the service environment loaded:
  * `OMP_THREAD_LIMIT=1 python3 scripts/financial_reader_recovery_estimate.py --case <case> --select-only`
    (seconds; selection counts only)
  * `OMP_THREAD_LIMIT=1 python3 scripts/financial_reader_recovery_estimate.py --case <case> --out /mnt/owl-data/fin-wt/r-recovery-estimate`
    (re-reads the selected originals; expect minutes per Andrews file under load)
  * `OMP_THREAD_LIMIT=1 python3 scripts/financial_ledger_misread_audit.py --case <case> --out /mnt/owl-data/fin-wt/r-recovery-audit [--limit N]`
    (937 admitted statement reviews live; only image-derived ones are re-read)

  Both scripts:
  * work inside a READ ONLY transaction (checked with `SHOW transaction_read_only`) and refuse ORM writes;
  * verify every original against its evidence hash before reading it;
  * read the originals in place and write only to a private scratch directory, which they delete;
  * report counts by reason. The audit report also carries source/evidence ids. Write both reports outside git.
* Which engine revision actually read the live batch is unknown until the live selection runs. The
  `unrecorded_reader` / `reader_not_affected` counts will show it. If live readings carry a digest that is not in
  the list (for example an uncommitted live build), they are not selected, by design.
* Live CAVEAT 2 (232 already-imported items in another batch) is handled as follows:
  * if those are the same evidence files, the files are excluded as `saved_import` / `several_batches`;
  * if they are re-uploaded copies, the estimator reports them as `identical_bytes_admitted`, and their periods
    would be held as duplicates by the ordinary gates.
* The engine also imports backend helpers (`services.financial.suspect_amounts`), and the processing record does
  not fingerprint those. The `pdf_extraction.py` digest is therefore a proxy for "reader revision".
* PG-only behaviour (row locks, `SHOW transaction_read_only`) is exercised only on SQLite here.

## Decisions taken (each reversible in one line)

1. **Flag default OFF** (`LOUPE_FINANCIAL_READER_RECOVERY`). I cannot prove the live effect without the live dry
   run. On the corpus it admitted 0 wrong periods (10 correct) and touched no edited or decided statement.
   Reverse: set the env var to `1` and restart. The snapshot then runs once per case at the next start.
2. **System re-reads use the batch's owner as the requesting actor.** The batch's Retry path attributes the new
   version and engine job to `batch.actor`, the same precedent as the 25 Sept follow-up campaign's
   `retry_failed_batches`. The batch entry's recovery record says `action='reader_recovery'` and names the
   release. Reverse: teach `_prepare_retry` to accept a system actor.
3. **A file with any ready period is left alone** (`not_all_held`). A new reading could change a period that is
   already ready, including holding it under the stricter money checks. Reverse: allow partial files, at the cost
   of re-reviewing ready periods.
4. **Integrator note:** if a later unit (for example `c-image`) edits `pdf_extraction.py`, add `e6526e20…` (the
   `7bd84c16` digest) to `AFFECTED_EXTRACTION_SHA256`.

## Needs Neil

* Run the live dry run and the live audit (commands above) and look at the counts.
* Then decide whether to turn on `LOUPE_FINANCIAL_READER_RECOVERY`.
* For any period the audit flags as **disagrees**, someone needs to compare the admitted value with the page.
  "disputed now only" is weaker evidence: on the corpus 3–4 of its 4–5 flags were correct periods on degraded
  scans.
