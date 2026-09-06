/**
 * The case's record of decisions, as rows on a screen.
 *
 * Every other financial screen shows the ledger as it stands now. This one
 * shows how it came to stand that way: what was set aside, what was hidden
 * behind a duplicate, what was deleted, who did each of those and on what
 * grounds. A row missing from a total is only defensible if the reason it is
 * missing can be produced, and until this existed the record held that reason
 * and nothing showed it.
 *
 * Presentational on purpose, like `IngestionRunsTable` and `LedgerTable`: it
 * draws records it is handed and fetches nothing, so every case below can be
 * put in front of it directly. `DecisionsPanel` is the half that fetches.
 *
 * Four things here are correctness rather than presentation.
 *
 * **The rows never appear without the sentence about their order.** They
 * arrive newest first by a timestamp written at the start of the transaction
 * that recorded them, so several decisions taken in one act carry it
 * identically and sit adjacent in an arbitrary order.
 * `DECISION_ORDER_IS_NOT_SEQUENCE` is rendered by this component rather than
 * by its caller for the same reason `RUN_COUNTS_ARE_HISTORY` is: whoever draws
 * the rows draws the caveat, so the two cannot be separated. Reading order off
 * this list across subjects would be a claim about who acted first that
 * nothing in the record supports.
 *
 * **The effect of a decision is rendered in words, never as a yes or a no.**
 * `changedStoredState` is three-valued, and null means this build does not
 * recognise the decision and so cannot say whether anything moved.
 * `readDecision` already resolves all three into `effect`, which is always
 * safe to render; a checkmark column here would have to choose what to draw
 * for null and the honest choice is a sentence. The value is still exposed as
 * a data attribute so tests can pin the three cases apart.
 *
 * **An unrecognised decision or subject renders loudly.** `readDecision` hands
 * back the `warning` variant for a decision it cannot read, the variant
 * reserved across the financial screens for "this build cannot read this
 * value", and the subject cell marks the same case rather than showing a bare
 * stored word as though it were a label.
 *
 * **The grounds are shown as written, and not summarised.** `reason` is what
 * the person typed at the time. It is the part of the entry that has to
 * survive being read back months later by someone else, so it is rendered
 * whole rather than truncated, and an empty one is named rather than left as
 * blank space that reads like no reason having been given.
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

import type { DecisionRecord } from "../api"
import {
  DECISION_ORDER_IS_NOT_SEQUENCE,
  formatDecisionTime,
  readDecidedBy,
  readDecision,
  readDecisionSubject,
} from "../lib/decision-format"

/** Reserved for "this build cannot read this value", as in `LedgerTable`. */
const UNRECOGNISED_VARIANT = "warning" as const

/**
 * `changedStoredState` as an attribute, keeping the three cases distinct.
 *
 * "null" rather than an absent attribute, so a test asserting the unknown case
 * fails when the attribute stops being written at all rather than passing on
 * the absence.
 */
function changedAttribute(changed: boolean | null): string {
  if (changed === null) return "null"
  return changed ? "true" : "false"
}

function DecisionRow({ record }: { record: DecisionRecord }) {
  const decision = readDecision(record.decision)
  const decisionUnrecognised = decision.value === null
  const subject = readDecisionSubject(record.subject_type)
  const subjectUnrecognised = subject.value === null
  const decidedBy = readDecidedBy(record)
  const reason = record.reason.trim()

  return (
    <TableRow data-testid="decision-row" data-decision-id={record.id}>
      <TableCell className="align-top">
        <div className="flex flex-col items-start gap-1">
          <Badge
            variant={decisionUnrecognised ? UNRECOGNISED_VARIANT : decision.variant}
            title={decision.description}
            data-testid="decision-badge"
            data-unrecognised={decisionUnrecognised ? "true" : "false"}
          >
            {decisionUnrecognised && <CircleHelp aria-hidden="true" />}
            {decision.label}
          </Badge>

          <p
            className="text-xs text-muted-foreground"
            data-testid="decision-effect"
            data-changed-stored-state={changedAttribute(decision.changedStoredState)}
          >
            {decision.effect}
          </p>

          {reason === "" ? (
            <p
              className="text-xs text-muted-foreground italic"
              data-testid="decision-no-reason"
              title={
                "The entry carries no grounds. Every other entry does, so this " +
                "one is incomplete rather than unexplained."
              }
            >
              No grounds recorded
            </p>
          ) : (
            <p className="text-xs break-words" data-testid="decision-reason">
              {reason}
            </p>
          )}
        </div>
      </TableCell>

      <TableCell className="align-top">
        <div className="flex flex-col items-start gap-1">
          <span
            className="text-sm"
            title={subject.description}
            data-testid="decision-subject"
            data-unrecognised={subjectUnrecognised ? "true" : "false"}
          >
            {subject.label}
          </span>
          <span
            className="font-mono text-xs break-all text-muted-foreground"
            data-testid="decision-subject-id"
          >
            {record.subject_id}
          </span>
          <span
            className="text-xs text-muted-foreground"
            data-testid="decision-sequence"
            title={
              "This is the nth decision about this one piece of evidence. That " +
              "numbering is the order they happened in, and it is reliable."
            }
          >
            Decision {record.subject_sequence} about this
          </span>
        </div>
      </TableCell>

      <TableCell className="align-top">
        <div className="flex flex-col items-start gap-1">
          <span
            className="text-sm"
            title={decidedBy.description}
            data-testid="decision-decided-by"
            data-by-machine={decidedBy.byMachine ? "true" : "false"}
          >
            {decidedBy.label}
          </span>
          {decidedBy.email !== null && (
            <span
              className="font-mono text-xs break-all text-muted-foreground"
              data-testid="decision-decided-by-email"
            >
              {decidedBy.email}
            </span>
          )}
        </div>
      </TableCell>

      <TableCell className="align-top whitespace-nowrap">
        <div className="font-mono text-xs" data-testid="decision-recorded-at">
          {formatDecisionTime(record.recorded_at)}
        </div>
      </TableCell>
    </TableRow>
  )
}

const COLUMN_COUNT = 4

export function DecisionsTable({ decisions }: { decisions: DecisionRecord[] }) {
  return (
    <div className="space-y-2">
      <Table data-testid="decisions-table">
        <TableHeader>
          <TableRow>
            <TableHead>Decision</TableHead>
            <TableHead>About</TableHead>
            <TableHead>Decided by</TableHead>
            <TableHead>Recorded</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {decisions.length === 0 ? (
            <TableRow>
              <TableCell
                colSpan={COLUMN_COUNT}
                className="text-center text-sm text-muted-foreground"
                data-testid="decisions-table-empty"
              >
                No decisions to show.
              </TableCell>
            </TableRow>
          ) : (
            decisions.map((record) => (
              <DecisionRow key={record.id} record={record} />
            ))
          )}
        </TableBody>
      </Table>

      {/*
        Drawn by this component and not by its caller, so a list of decisions
        can never be rendered without it. See the docstring.
      */}
      <p className="text-xs text-muted-foreground" data-testid="decision-order-caveat">
        {DECISION_ORDER_IS_NOT_SEQUENCE}
      </p>
    </div>
  )
}
