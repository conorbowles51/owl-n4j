/**
 * Reading an ingestion run for display.
 *
 * A run is one attempt to load evidence into the ledger. The row it leaves
 * behind says who started it, when, how much it saw, and, if it broke, what
 * broke it. This module turns that row into English.
 *
 * Three things it deliberately does not do.
 *
 * **It does not judge staleness.** A run that says `running` is reported as
 * running, with the time it started, and nothing more is claimed. Deciding
 * that a run has in fact been abandoned belongs to `reap_stale_runs` on the
 * backend, which writes that decision down. A second opinion formed here would
 * have no record behind it and would disagree with the recorded one the moment
 * either threshold moved.
 *
 * **It does not reconcile the counts.** `documents_seen`,
 * `transactions_admitted` and `transactions_quarantined` are what the run
 * recorded when it ended. Adjudication moves rows afterwards, so comparing them
 * against the ledger as it stands now answers a different question than the one
 * the run was asked. They are reported as history, and `RUN_COUNTS_ARE_HISTORY`
 * is the sentence that says so on screen.
 *
 * **It does not rank runs.** Which run matters is a question about the case,
 * and `needsAttention` only says whether a given run ended in a way somebody
 * should be told about.
 *
 * Narrowing goes through `ledger-format.ts` rather than being repeated here, so
 * a status this build has never heard of is handled the same way it is
 * everywhere else: named, marked unrecognised, never rendered blank.
 */

import {
  INGESTION_RUN_STATUSES,
  type IngestionRun,
  type IngestionRunStatus,
} from "../api"
import { narrow, type NarrowedTerm, type TermCopy } from "./ledger-format"
import type { Badge } from "@/components/ui/badge"
import type { ComponentProps } from "react"

type BadgeVariant = NonNullable<ComponentProps<typeof Badge>["variant"]>

/**
 * Why the three counts on a run are never checked against the ledger.
 *
 * Held here as one string so the screen and the tests say the same thing.
 */
export const RUN_COUNTS_ARE_HISTORY =
  "These are the figures this attempt recorded when it ended. Rows can be set " +
  "aside or reinstated afterwards, so they are a record of the attempt and not " +
  "a count of what is in the ledger now."

const RUN_STATUS_COPY: Record<IngestionRunStatus, TermCopy> = {
  pending: {
    label: "Not started",
    description:
      "The attempt was opened but had not begun reading anything. Nothing from it has reached the ledger.",
  },
  running: {
    label: "In progress",
    description:
      "The attempt is still open. What it has taken in so far may be incomplete, and its figures are not final until it ends.",
  },
  completed: {
    label: "Finished",
    description:
      "The attempt ran to the end. What it took in is in the ledger and can be traced back to the files it read.",
  },
  failed: {
    label: "Broke",
    description:
      "The attempt stopped part way because something went wrong. Anything it had already taken in is in the ledger, and anything it had not reached is missing from it.",
  },
  aborted: {
    label: "Stopped",
    description:
      "The attempt was ended deliberately rather than breaking. As with one that broke, it stopped part way, so the material it was working through is only partly in the ledger.",
  },
}

/**
 * `Badge` falls through to its `default` variant -- a loud filled primary --
 * for any key a variant map does not carry, so a status missing from this table
 * would render as the most important thing on the screen rather than failing
 * loudly. `Record<IngestionRunStatus, ...>` makes the compiler notice instead.
 */
const RUN_STATUS_VARIANT: Record<IngestionRunStatus, BadgeVariant> = {
  pending: "slate",
  running: "info",
  completed: "success",
  failed: "danger",
  aborted: "warning",
}

export interface RunStatusReading extends NarrowedTerm<IngestionRunStatus> {
  variant: BadgeVariant
  /**
   * True when the attempt ended without finishing, or has not ended at all. A
   * caller has grounds to put such a run in front of a reader who did not ask
   * for it, because in each of these cases the ledger holds less than the
   * evidence that was handed to it.
   *
   * False for an unrecognised status. This build cannot say what an unknown
   * word means, and guessing that it is bad would raise an alarm about a run
   * that may have been perfectly fine.
   */
  needsAttention: boolean
}

const NEEDS_ATTENTION: ReadonlySet<IngestionRunStatus> =
  new Set<IngestionRunStatus>(["pending", "running", "failed", "aborted"])

export function readRunStatus(raw: string): RunStatusReading {
  const term = narrow(
    raw,
    INGESTION_RUN_STATUSES,
    RUN_STATUS_COPY,
    "the ingestion record"
  )
  if (term.value === null) {
    return { ...term, variant: "outline", needsAttention: false }
  }
  return {
    ...term,
    variant: RUN_STATUS_VARIANT[term.value],
    needsAttention: NEEDS_ATTENTION.has(term.value),
  }
}

/* ------------------------------------------------------------------ *
 * The rest of the row
 * ------------------------------------------------------------------ */

/**
 * Who started the run.
 *
 * The email is preferred over the user id because the foreign key nulls when an
 * account is deleted and the email does not; the writer records both for
 * exactly that reason. When neither survives, this says so rather than
 * rendering an empty space, which would read as nobody having started it.
 */
export function readRunStarter(run: IngestionRun): string {
  if (run.started_by_email) return run.started_by_email
  if (run.started_by_user_id) return `User ${run.started_by_user_id}`
  return "Not recorded"
}

/**
 * A stored timestamp as a readable date and time, or a stated absence.
 *
 * Fixed to a single locale rather than the browser's, matching
 * `formatLedgerAmount`, so the same run reads the same way on every machine
 * that opens the case. An unparseable value is shown as it arrived instead of
 * as "Invalid Date".
 */
export function formatRunTime(value: string | null): string {
  if (!value) return "Not recorded"
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return parsed.toLocaleString("en-GB", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })
}

/**
 * How long the attempt took, or why that cannot be said.
 *
 * Null when either end is missing or the pair is out of order. A run still
 * open has no duration yet, and a negative one would mean the two timestamps
 * disagree, which is worth showing as nothing rather than as a negative
 * number of minutes.
 */
export function runDuration(run: IngestionRun): string | null {
  if (!run.started_at || !run.completed_at) return null
  const start = new Date(run.started_at).getTime()
  const end = new Date(run.completed_at).getTime()
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return null

  const seconds = Math.round((end - start) / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ${seconds % 60}s`
  return `${Math.floor(minutes / 60)}h ${minutes % 60}m`
}

/** Known non-import work must not imply missing imported transactions. */
export function isProvisionalAccountRun(run: IngestionRun): boolean {
  return (
    run.config.operation === "provisional_candidate_account" &&
    run.documents_seen === 0 &&
    run.transactions_admitted === 0 &&
    run.transactions_quarantined === 0
  )
}

export function readRunOperationStatus(run: IngestionRun): RunStatusReading {
  const status = readRunStatus(run.status)
  if (!isProvisionalAccountRun(run) || status.value === null) return status
  const descriptions: Record<IngestionRunStatus, string> = {
    pending:
      "Provisional account setup has not started. This operation does not import transactions.",
    running:
      "Provisional account setup is still open. Check its recorded outcome before retrying; this operation does not import transactions.",
    completed:
      "Provisional account setup completed. The account label and reason were recorded; no transactions were imported by this operation.",
    failed:
      "Provisional account setup did not complete successfully. Check the recorded error and current accounts before retrying. This operation does not import transactions.",
    aborted:
      "Provisional account setup was stopped. Check current accounts before retrying; this operation does not import transactions.",
  }
  return {
    ...status,
    description: descriptions[status.value],
    label: status.value === "failed" ? "Setup not completed" : status.label,
  }
}
