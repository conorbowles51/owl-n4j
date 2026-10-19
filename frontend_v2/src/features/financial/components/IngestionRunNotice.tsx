/**
 * The attempts that did not finish, said out loud above the ledger.
 * Known provisional-account setup is identified separately: it records an audit
 * attempt but cannot establish a gap in imported transactions.
 *
 * An ingestion run is one attempt to put evidence into the ledger. Until this
 * existed, an attempt that broke part way through a statement left no trace on
 * any screen: the ledger simply held fewer rows than the file contained, and
 * looked exactly like a ledger that was complete. This is the component that
 * refuses to let that happen quietly.
 *
 * **It says nothing at all when there is nothing to say.** Silence is the
 * normal output. Only a run whose status carries `needsAttention` puts anything
 * on screen, and that flag is deliberately false for a status this build does
 * not recognise, so a backend one version ahead cannot make this component
 * raise an alarm about an ending it cannot read. See `readRunStatus`.
 *
 * **A failed read is not silence.** If the run history itself cannot be
 * fetched, this says so. Rendering nothing in that case would be the component
 * asserting that nothing went wrong, on the strength of a request that never
 * came back — which is the one claim it must never make.
 *
 * **It carries no counts.** `documents_seen`, `transactions_admitted` and
 * `transactions_quarantined` are what a run recorded when it ended, not a count
 * of the ledger as it stands, and they may never appear without the sentence in
 * `RUN_COUNTS_ARE_HISTORY` explaining that. That sentence is too long to sit
 * above a table in a warning, so the counts live on the attempts list instead
 * and this stays short.
 *
 * **It is not truncated.** A case with six broken attempts produces six
 * entries. That is a long notice, and it is the correct one: the length is
 * proportional to how much of the evidence may be missing.
 *
 * **It must be mounted beside `LedgerPanel`, never inside it.** The panel
 * returns early for no case, for a read in flight, for a failed read and for
 * zero rows, so anything nested within it vanishes exactly when the ledger is
 * empty — which is precisely the moment a broken attempt is the explanation for
 * the emptiness.
 *
 * No limit is sent with the request, so this is looking at every attempt
 * recorded against the case rather than a recent window of them, and shares one
 * fetch with the attempts list under the same query key.
 */

import { CircleAlert, TriangleAlert } from "lucide-react"

import { Badge } from "@/components/ui/badge"

import type { IngestionRun } from "../api"
import { useIngestionRuns } from "../hooks/use-ingestion-runs"
import {
  formatRunTime,
  readRunStarter,
  readRunOperationStatus,
  isProvisionalAccountRun,
} from "../lib/run-format"

/**
 * One flagged attempt.
 *
 * Every run reaching here has a recognised status, because `needsAttention` is
 * false for one that does not, so the badge variant is always a mapped one and
 * there is no unrecognised branch to draw.
 */
function FlaggedRun({ run }: { run: IngestionRun }) {
  const status = readRunOperationStatus(run)

  return (
    <li
      className="border-l-2 border-current/25 pl-3"
      data-testid="run-notice-item"
      data-run-key={run.key}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={status.variant} data-testid="run-notice-status">
          {status.label}
        </Badge>
        <span className="text-xs" data-testid="run-notice-detail">
          Started {formatRunTime(run.started_at)} by {readRunStarter(run)}
        </span>
      </div>

      <p className="mt-1 text-xs" data-testid="run-notice-description">
        {status.description}
      </p>

      {run.error !== null && run.error !== "" && (
        <p
          className="mt-1 font-mono text-xs break-words"
          data-testid="run-notice-error-text"
        >
          {run.error}
        </p>
      )}
    </li>
  )
}

export function IngestionRunNotice({ caseId }: { caseId: string | undefined }) {
  const { data, isPending, isError, error } = useIngestionRuns(caseId)

  /*
   * No case and a read in flight both render nothing. `LedgerPanel` already
   * says which of the two the screen is in, and a second voice saying it beside
   * the first is noise. Neither is a state in which this component has grounds
   * to raise an alarm or to give the all-clear.
   */
  if (!caseId || isPending) return null

  if (isError) {
    return (
      <div
        className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
        data-testid="run-notice-read-failed"
      >
        <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span>
          The record of past attempts to load this ledger could not be read, so
          nothing here says whether everything sent to it arrived.
          {error instanceof Error ? ` ${error.message}` : ""}
        </span>
      </div>
    )
  }

  const flagged = data.runs.filter(
    (run) => readRunOperationStatus(run).needsAttention
  )
  if (flagged.length === 0) return null

  const setupCount = flagged.filter(isProvisionalAccountRun).length
  const importCount = flagged.length - setupCount
  const one = importCount === 1

  return (
    <div
      className="space-y-2 rounded-md border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-amber-900 dark:text-amber-200"
      data-testid="run-notice"
      role="status"
    >
      <p className="flex items-start gap-2 text-sm font-medium">
        <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
        <span data-testid="run-notice-headline">
          {importCount > 0 ? (
            <>
              {one
                ? "One attempt to load evidence into this ledger has not finished."
                : `${importCount} attempts to load evidence into this ledger have not finished.`}{" "}
              The ledger below can therefore hold less than the evidence{" "}
              {one ? "it was" : "they were"} given.
              {setupCount > 0 &&
                ` Also, ${setupCount} provisional account setup ${setupCount === 1 ? "attempt needs" : "attempts need"} attention; account setup does not import transactions.`}
            </>
          ) : (
            <>
              {setupCount === 1
                ? "One provisional account setup needs attention."
                : `${setupCount} provisional account setup attempts need attention.`}{" "}
              Account setup does not import transactions; this is not evidence
              of missing imported rows.
            </>
          )}
        </span>
      </p>

      <ul className="space-y-2">
        {flagged.map((run) => (
          <FlaggedRun key={run.key} run={run} />
        ))}
      </ul>
    </div>
  )
}
