/**
 * Every attempt to load evidence into the ledger, as rows on a screen.
 *
 * The notice above the ledger speaks only when something broke. This is the
 * other half: the whole history, successes included. A reader asking whether
 * the ledger is complete cannot answer it from the failures alone, because a
 * ledger with no failures against it and no attempts against it either look
 * identical from the ledger side.
 *
 * Presentational on purpose, like `LedgerTable`: it draws runs it is handed and
 * fetches nothing, so every case below can be put in front of it directly.
 * `IngestionRunsPanel` is the half that fetches.
 *
 * Four things here are correctness rather than presentation.
 *
 * **The counts never appear without the sentence that qualifies them.**
 * `documents_seen`, `transactions_admitted` and `transactions_quarantined` were
 * true when the run ended, and adjudication moves rows afterwards, so they will
 * legitimately disagree with the ledger as it stands. `RUN_COUNTS_ARE_HISTORY`
 * is rendered by this component rather than by its caller precisely so the two
 * cannot be separated: whoever draws the numbers draws the sentence.
 *
 * **An unrecognised status renders loudly.** The notice stays silent on a
 * status this build has never heard of, which is right for a warning and wrong
 * here: a list whose job is to show every attempt cannot quietly show one it
 * could not read. `readRunStatus` hands back the `outline` variant for that
 * case, a safe neutral for a caller that might place the badge anywhere; this
 * table overrides it to `warning`, the variant `LedgerTable` reserved for "this
 * build cannot read this value", so one colour keeps one meaning across the
 * financial screens.
 *
 * **A run with no end is said to have no end, not shown as instant.** The read
 * makes no staleness judgement and neither does this: a run whose
 * `completed_at` is null is reported as having no end recorded, with the time
 * it started, and nothing is claimed about whether it is still working.
 *
 * **A length that cannot be stated is stated as such.** `runDuration` returns
 * null when the two timestamps disagree or will not parse, and a blank cell
 * there would read as a run that took no time.
 */

import { CircleHelp } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

import type { IngestionRun } from "../api"
import {
  RUN_COUNTS_ARE_HISTORY,
  formatRunTime,
  readRunStarter,
  readRunStatus,
  runDuration,
} from "../lib/run-format"

/** Reserved for "this build cannot read this value", as in `LedgerTable`. */
const UNRECOGNISED_VARIANT = "warning" as const

function RunRow({ run }: { run: IngestionRun }) {
  const status = readRunStatus(run.status)
  const unrecognised = status.value === null
  const duration = runDuration(run)

  return (
    <TableRow data-testid="run-row" data-run-key={run.key}>
      <TableCell className="align-top">
        <div className="flex flex-col items-start gap-1">
          <Badge
            variant={unrecognised ? UNRECOGNISED_VARIANT : status.variant}
            title={status.description}
            data-testid="run-status"
            data-unrecognised={unrecognised ? "true" : "false"}
          >
            {unrecognised && <CircleHelp aria-hidden="true" />}
            {status.label}
          </Badge>

          {run.error !== null && run.error !== "" && (
            <p
              className="font-mono text-xs break-words text-destructive"
              data-testid="run-error"
            >
              {run.error}
            </p>
          )}

          {run.notes !== null && run.notes !== "" && (
            <p className="text-xs break-words text-muted-foreground" data-testid="run-notes">
              {run.notes}
            </p>
          )}
        </div>
      </TableCell>

      <TableCell className="align-top whitespace-nowrap">
        <div className="font-mono text-xs" data-testid="run-started">
          {formatRunTime(run.started_at)}
        </div>
        <div className="text-xs text-muted-foreground" data-testid="run-starter">
          {readRunStarter(run)}
        </div>
      </TableCell>

      <TableCell className="align-top whitespace-nowrap">
        {run.completed_at === null ? (
          <span
            className="text-xs text-muted-foreground italic"
            data-testid="run-no-end"
            title={
              "No ending was recorded against this attempt. That is all this " +
              "says: it is not a claim that the attempt is still working."
            }
          >
            No end recorded
          </span>
        ) : (
          <>
            <div className="font-mono text-xs" data-testid="run-ended">
              {formatRunTime(run.completed_at)}
            </div>
            {duration === null ? (
              <div
                className="text-xs text-muted-foreground italic"
                data-testid="run-no-duration"
                title={
                  "The recorded start and end do not make a length that can be " +
                  "stated, so none is shown rather than showing a wrong one."
                }
              >
                Length not known
              </div>
            ) : (
              <div className="text-xs text-muted-foreground" data-testid="run-duration">
                {duration}
              </div>
            )}
          </>
        )}
      </TableCell>

      <TableCell className="align-top text-right tabular-nums" data-testid="run-documents-seen">
        {run.documents_seen}
      </TableCell>
      <TableCell className="align-top text-right tabular-nums" data-testid="run-admitted">
        {run.transactions_admitted}
      </TableCell>
      <TableCell className="align-top text-right tabular-nums" data-testid="run-quarantined">
        {run.transactions_quarantined}
      </TableCell>
    </TableRow>
  )
}

const COLUMN_COUNT = 6

export function IngestionRunsTable({ runs }: { runs: IngestionRun[] }) {
  return (
    <div className="space-y-2">
      <Table data-testid="runs-table">
        <TableHeader>
          <TableRow>
            <TableHead>Attempt</TableHead>
            <TableHead>Started</TableHead>
            <TableHead>Ended</TableHead>
            <TableHead className="text-right">Documents seen</TableHead>
            <TableHead className="text-right">Rows admitted</TableHead>
            <TableHead className="text-right">Rows set aside</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {runs.length === 0 ? (
            <TableRow>
              <TableCell
                colSpan={COLUMN_COUNT}
                className="text-center text-sm text-muted-foreground"
                data-testid="runs-table-empty"
              >
                No attempts to show.
              </TableCell>
            </TableRow>
          ) : (
            runs.map((run) => <RunRow key={run.key} run={run} />)
          )}
        </TableBody>
      </Table>

      {/*
        Drawn by this component and not by its caller, so the three count
        columns above can never be rendered without it. See the docstring.
      */}
      <p className="text-xs text-muted-foreground" data-testid="run-counts-are-history">
        {RUN_COUNTS_ARE_HISTORY}
      </p>
    </div>
  )
}
