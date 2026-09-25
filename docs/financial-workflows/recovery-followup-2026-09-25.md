# Bounded follow-up for unresolved Financial work

Campaign: `statement-recovery-2026-09-25-unresolved-v1`.

The initial recovery campaign is durable and does not repeat after a code update.
This follow-up is a separate one-time snapshot for the user's existing-data
backfill request. It retains the original run, its receipts and all source work.
The Andrews OCR-specific campaign remains registered but dormant.

## Repair of an empty, historically protected snapshot

`statement-recovery-2026-09-25-restored-v2` applies only when the v1 run is
complete, has no recovery items, and its durable scope records every considered
source as protected with none scheduled. Running, paused, partly scheduled or
successful recovery runs are not replayed.

The repair recognizes an explicit current branch only from a verified Process
PDF afresh request tied to its removal receipt and investigator, or a matching
case/file/revision restore audit. A newer visible reading alone is insufficient.
Retired batches, hidden ancestors and rejected imports remain in history; their
records are never reopened or used as targets for automatic additions. Every
existing failed-batch source and prepared-reading reference must be inside the
reopened branch. Missing or mismatched reset references still require review;
a same-name upload is never substituted.

Current removals, skips, duplicate ignores, pending edits and active/paused work
remain protected. The branch receipt is checked again before execution, and a
changed receipt stops recovery for comparison. Sources without verified reset
or restore provenance remain protected. Consequently this repair does not
promise that every visible historical source will be scheduled; its actual
scope and outcomes must be verified after deployment.

## Eligibility and execution

The snapshot considers case-owned Financial source families created before its
durable activation cutoff. Only verified same-case, byte-identical reading
lineage is grouped. Matching filenames or independently uploaded matching bytes
do not establish shared history.

A family must have an earlier recovery result still needing review or a terminal
failed batch entry, and one of:

- Recorded explicit investigator Financial selection.
- An existing admitted Financial source record.
- A statement layout recognized from retained printed source geometry.

Old batch membership, file extension, folder name and the mere presence of text
do not establish financial content. Unknown content is counted and not processed.
Removed sources/imports, skipped periods and ignored duplicates are excluded;
the same choices are checked again at execution. A direct single-statement
duplicate ignore protects its entire mixed reading. Successful sources without
an unresolved failure are left unchanged. The snapshot, including an empty one,
is durable and cannot expand on restart.

An eligible stale batch error is handed to the existing durable Retry operation.
Readable retained data re-prepares reviews without an engine job. A failed or
missing reading may use its existing retry path. The batch receipt and recovery
item commit together, and each failure is handed off once. A repeated failure
becomes an actionable review result, not an automatic retry loop. An extant
source/prepared reference outside verified lineage is never substituted.

Active readings, active batch units, pending imports and paused work retain their
owner and pause state. Recovery waits for them. Newer investigator readings are
left for comparison. Missing originals get an unavailable-source explanation.

New statements are prepared for investigator review and never auto-imported.
For existing partial imports, the current reader and strict additive planner may
append only provably missing, reconciled payments. Existing transaction IDs,
corrections, exclusions, notes and receipts remain. Unresolved manual additions,
pending batch corrections, conflicting values, overlapping sources, or failed
reconciliation prevent automatic additions and explain the review requirement.
No amounts are inferred to make balances match.

## Status contract

The existing recovery status response adds optional top-level `scope`:

```json
{
  "considered": 100,
  "scheduled": 20,
  "protected": 10,
  "no_unresolved_work": 65,
  "unconfirmed_content": 5
}
```

All five values are nonnegative integer counts of source families at snapshot
time, not statement periods or payments. `considered` equals the sum of the other
four. `protected` includes explicit removal/skip/duplicate dispositions.
`unconfirmed_content` means unresolved work with no qualifying recorded selection,
admitted import or recognized retained statement; it does not mean non-financial.
`no_unresolved_work` means no qualifying earlier review or terminal batch failure,
not a claim that every source has been independently verified.

`scope` is null or absent for older campaigns. Existing `total`, `counts`, `items`
and `added` describe only scheduled recovery items/results. Completion means the
scheduled attempts finished; review outcomes and unconfirmed content may remain.
The case-level ingestion audit stores the same scope with operation
`statement_recovery_followup_snapshot`, release and run ID. Previous runs remain
available through the existing history/status contract.

## Acceptance and limits

### Saved replacement readings

An available newer reading is distinct from one whose payments may enter
Transactions. The preview exposes `current_import.refresh_admission` using the
final assigned rows and the same replacement request as confirmation, including
the investigator's saved controls and explicitly cleared details. The separate
`refresh_requires_reconciliation` flag is true whenever any payment row remains
selected, even when none is yet usable.

The replacement panel shows the saved-balance calculation and exact blockers.
Payment saving is disabled for missing, pending or failed assessments. Review
saved details and balances opens and focuses the saved editor; saving corrections
refreshes the assessment. A prior-draft comparison still requires an explicit
acknowledgment bound to the current reading/import/draft revisions. Reopening
does not waive it. Source-only balance observations can still be saved without
claiming a reconciled statement or confirmed no activity. Confirmation rechecks
the strict payment gate and retains the earlier source and edits.

An explicit saved currency correction also remains authoritative. A conflicting
reading exposes `current_import.refresh_currency_conflict` with `saved_currency`,
`reading_currency` and an actionable message; it cannot report replacement
readiness or overwrite the saved denomination. This applies to both the same
reading and a new retained evidence version. **Check this reading in saved JPY**
(example currency) reruns the read-only preview with that currency and focuses the
result. It makes no payment or balance write and performs no currency conversion.
The investigator must still resolve the saved-control blockers and deliberately
confirm the replacement. Historical imports with no explicit currency correction
may use an improved reader's denomination; preserved saved balance values are
rescaled by the denomination's decimal places to retain the same printed number.

The currency workflow is covered by a synthetic real-browser journey at 390px:
conflict → read-only saved-currency check → remaining exact balance difference →
correct saved controls → ready → reopen → deliberate payment save. Companion
backend checks prove preview/POST parity and protect explicit correction history.

Synthetic tests cover partial additions and stable IDs, duplicate retry receipt
handling, rollback atomicity, saved corrections, manual additions, exclusions,
paused/active work, late duplicate/removal decisions, unknown/malformed source
content, unrelated prepared references, and unavailable originals. Actual
production eligibility totals and recovered counts must be read after deployment;
local tests do not establish that every historical statement can reconcile.

The known old CAAL failure can be re-prepared automatically only when its actual
stored references satisfy these conditions. A same-name replacement upload is
not sufficient. Unsupported readers, unresolved OCR values, conflicting reviews,
unknown content and missing source identity remain explicit investigator work.
