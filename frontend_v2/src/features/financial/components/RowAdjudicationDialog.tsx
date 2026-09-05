/**
 * Setting one ledger row aside, or letting it back in, on a person's authority.
 *
 * This is the first thing in the frontend a person can actually see and use in
 * the quarantine work.  The three commits before it built the call, the reader
 * that turns the answer into words, and the mutation that makes the call; all
 * of it was reachable only from a test.  This is the surface.
 *
 * Which of the two changes this dialog offers is read off the row, not passed
 * in
 * ----------------------------------------------------------------------------
 *
 * A `ledger_status` of `quarantined` means the only change available is
 * letting the row back in; anything else means the only change available is
 * setting it aside.  The row already carries that status, so taking the verb
 * as a prop would be a second copy of a fact the row states, and the two can
 * disagree — a caller that passed "set aside" for a row already held would ask
 * the ledger to do something it has already done and get "no change" back,
 * having told the person a question was being asked that was not.  Reading it
 * off the row makes that impossible.
 *
 * A status this build cannot read gets neither verb.  Not a refusal on the
 * ledger's behalf: it is that the change to offer is *derived* from the status,
 * so a status that cannot be read leaves nothing to derive it from, and a
 * guess here would send a write nobody asked for.  The row is still drawn and
 * the raw value is still shown.
 *
 * Non-admitted rows are not screened out.  A superseded row offered "set
 * aside" will be refused by the ledger, and that refusal is shown as the
 * ledger's own answer rather than pre-empted here.  A second copy of the
 * ledger's rules in the browser is a second thing to keep in step, and the one
 * that drifts is the copy.
 *
 * Why the reason field is required here when the hook does not require it
 * ----------------------------------------------------------------------
 *
 * `useRowAdjudication` deliberately passes `reason` through unexamined,
 * because the endpoint requires the field and not its content.  The guard was
 * left for this layer, and it is not a rule invented in the browser.  Every
 * writer underneath refuses a blank one, in four separate places: the grounds
 * a person takes responsibility for (`QuarantineBasis.from_adjudication`),
 * the release path, the code that appends the decision, and a check
 * constraint on the table itself.  What the first three do with it is return
 * an ordinary refusal, so a blank reason typed here and sent anyway comes back
 * as a 200 saying it was not done.  Disabling the button spares a person a
 * round trip whose only possible answer is no.
 *
 * The guard is at least as strict as the database's own and never the other
 * way round.  The stored check treats tabs, carriage returns and newlines as
 * blank; `trim` treats those and a few more besides as blank.  So a string
 * this dialog rejects might have been accepted, but nothing it accepts can hit
 * a constraint the person cannot see or act on, which is the direction that
 * matters.
 *
 * What is sent is the trimmed text, which is also what would be stored
 * regardless: the writer builds its detail as `"<actor>: <reason.strip()>"`.
 * Trimming here means the words that go on the record are the words the guard
 * checked.
 *
 * What the answer says, and what it is not allowed to say
 * ------------------------------------------------------
 *
 * A refusal arrives as a 200.  Only a missing row and a failed write throw.
 * So this dialog never reports success from the mutation resolving; whether
 * the row moved is `applied`, and that is the only field the sentence about it
 * comes from.  `readRowAdjudication` also reads the outcome word itself, and
 * where the two contradict each other the contradiction is shown rather than
 * settled by preferring one.
 *
 * Whether taking the row out balanced its statement is said in this answer and
 * in no other place — deliberately not on the record, because an observation
 * the system made must not end up filed as a person's finding.  If this dialog
 * drops it, it is not anywhere.  So it is rendered whenever the reading has
 * anything to say, and suppressed only for the case that carries no fact about
 * a statement at all: nothing came out of the ledger, so no removal was
 * checked against one.
 *
 * The text in `reason` is never the person's own words on any outcome, and
 * `ADJUDICATION_REASON_IS_NEVER_THE_PERSONS` goes beside it wherever it is
 * shown, so nobody reads the system's wording back as somebody's stated
 * grounds.
 *
 * A note for whoever wires this up
 * --------------------------------
 *
 * A successful change invalidates the ledger lists, so the row will move
 * between them and the list this dialog was opened from will refetch without
 * it.  The answer lives in the mutation, which lives here, so a caller that
 * unmounts the dialog when its row leaves the list destroys the answer before
 * it has been read — and the statement-balance fact with it.  Keep it mounted
 * until the person closes it.
 */

import { CircleHelp, TriangleAlert } from "lucide-react"
import { useState } from "react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { LoadingSpinner } from "@/components/ui/loading-spinner"
import { Textarea } from "@/components/ui/textarea"

import {
  useRowAdjudication,
  type AdjudicationAction,
} from "../hooks/use-row-adjudication"
import {
  ADJUDICATION_REASON_IS_NEVER_THE_PERSONS,
  type RowAdjudicationReading,
} from "../lib/adjudication-format"
import {
  changeAvailableFor,
  formatLedgerAmount,
  readDirection,
  readLedgerStatus,
  ROW_CHANGE_LABELS,
  type NarrowedTerm,
} from "../lib/ledger-format"
import type { LedgerTransaction } from "../api"

/** Reserved for "this build cannot read this value", matching `LedgerTable`. */
const UNRECOGNISED_VARIANT = "warning" as const

interface ActionCopy {
  title: string
  /** What the change does, in the terms a person weighing it needs. */
  blurb: string
  reasonLabel: string
  reasonHelp: string
  submit: string
}

const ACTION_COPY: Record<AdjudicationAction, ActionCopy> = {
  quarantine: {
    title: "Set this row aside",
    blurb:
      "The row stays in the case and stays readable, and it leaves every total, search and money flow this case reports. A decision naming you and your grounds goes on the record.",
    reasonLabel: "Why this row should not be counted",
    reasonHelp:
      "Required. This goes on the record against your name and stays readable for as long as the case does, so write it for someone reading it later without you there.",
    submit: ROW_CHANGE_LABELS.quarantine,
  },
  release: {
    title: "Let this row back in",
    blurb:
      "The row counts toward totals again. This is not an undo: the setting aside stays on the record and the reversal is recorded after it, so the record holds both and who took each.",
    reasonLabel: "Why this row should count again",
    reasonHelp:
      "Required. A row let back in carries no trace of having been held, so the record is the only place this will be explained.",
    submit: ROW_CHANGE_LABELS.release,
  },
}

/** One narrowed value as a badge, on the same rule as `LedgerTable`. */
function TermBadge({
  term,
  variant,
  testId,
}: {
  term: NarrowedTerm<string>
  variant: "outline" | "slate" | "amber" | "success" | "danger" | "info"
  testId: string
}) {
  const unrecognised = term.value === null
  return (
    <Badge
      variant={unrecognised ? UNRECOGNISED_VARIANT : variant}
      title={term.description}
      data-testid={testId}
      data-unrecognised={unrecognised ? "true" : "false"}
    >
      {unrecognised && <CircleHelp aria-hidden="true" />}
      {term.label}
    </Badge>
  )
}

/**
 * The row, said back to the person before they commit to changing it.
 *
 * Enough to recognise it by and no more: the date the ledger orders by, what
 * the statement called it, the amount and which way it went.  An unscaled
 * amount is marked here for the reason it is marked in the table — the figure
 * is a count of minor units rather than a sum of money, and rendering it
 * unmarked shows 123456 where 1,234.56 belongs.
 */
function RowIdentity({
  row,
  status,
}: {
  row: LedgerTransaction
  status: NarrowedTerm<string>
}) {
  const amount = formatLedgerAmount(row.amount_minor, row.currency)
  const direction = readDirection(row.direction)

  return (
    <div
      className="rounded-md border border-border/70 bg-muted/30 p-3"
      data-testid="adjudication-row"
      data-row-key={row.key}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="font-mono text-xs text-muted-foreground">
            {row.ordering_date}
          </div>
          {row.description === null ? (
            <span
              className="text-xs text-muted-foreground italic"
              data-testid="adjudication-no-description"
              title="The ledger holds no description for this row."
            >
              No description recorded
            </span>
          ) : (
            <span className="text-sm">{row.description}</span>
          )}
          {row.counterparty_raw !== null && (
            <div
              className="text-xs text-muted-foreground"
              data-testid="adjudication-counterparty"
            >
              {row.counterparty_raw}
            </div>
          )}
        </div>
        <div className="shrink-0 text-right">
          <div className="font-mono text-sm tabular-nums" data-testid="adjudication-amount">
            {amount.text}{" "}
            <span className="text-xs text-muted-foreground">{amount.currency}</span>
          </div>
          {!amount.scaled && (
            <Badge
              variant="warning"
              className="mt-1"
              data-testid="adjudication-amount-unscaled"
              title={
                "This figure is the stored count of minor units, not an amount. " +
                "It could not be scaled, so read it against the source document " +
                "before relying on it."
              }
            >
              <TriangleAlert aria-hidden="true" />
              Unscaled
            </Badge>
          )}
        </div>
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <TermBadge
          term={direction}
          variant={direction.value === "credit" ? "info" : "slate"}
          testId="adjudication-direction"
        />
        <TermBadge
          term={status}
          variant={
            status.value === "admitted"
              ? "success"
              : status.value === "quarantined"
                ? "amber"
                : status.value === "rejected"
                  ? "danger"
                  : "slate"
          }
          testId="adjudication-current-status"
        />
      </div>
    </div>
  )
}

/**
 * What the ledger answered, in the order a person needs it.
 *
 * Outcome first, then whether anything actually moved, because those are two
 * different questions and only the second one is `applied`.  Then the ledger's
 * own wording with the note about whose wording it is, then the statement
 * check, then where the row now stands, then the id of the decision that was
 * appended.
 */
function AdjudicationAnswer({ reading }: { reading: RowAdjudicationReading }) {
  return (
    <div
      className="space-y-3 rounded-md border border-border/70 bg-muted/30 p-3"
      data-testid="adjudication-answer"
      data-outcome={reading.outcome.raw}
      data-applied={reading.applied ? "true" : "false"}
    >
      <div className="flex items-center gap-2">
        <Badge
          variant={reading.outcome.variant}
          data-testid="adjudication-outcome"
          data-unrecognised={reading.outcome.value === null ? "true" : "false"}
        >
          {reading.outcome.value === null && <CircleHelp aria-hidden="true" />}
          {reading.outcome.label}
        </Badge>
        {/* Said from `applied` and from nothing else. The outcome word is read
            separately and a disagreement between the two is reported below
            rather than resolved by preferring either. */}
        <span className="text-xs font-medium" data-testid="adjudication-moved">
          {reading.applied
            ? "This row's standing changed."
            : "Nothing about this row changed."}
        </span>
      </div>

      <p className="text-xs text-muted-foreground">{reading.outcome.description}</p>

      {reading.appliedDisagreesWithOutcome && (
        <p
          className="rounded-md border border-destructive/40 bg-destructive/5 p-2 text-xs"
          data-testid="adjudication-disagreement"
        >
          The ledger&rsquo;s answer contradicts itself: the outcome it named and
          its own record of whether anything was written do not agree. Check the
          row and the record before relying on either, and report this.
        </p>
      )}

      <div data-testid="adjudication-reason" data-reason-kind={reading.reason.kind}>
        <p className="text-xs font-medium">{reading.reason.heading}</p>
        {reading.reason.text !== null && (
          <>
            <p className="mt-1 text-xs text-muted-foreground">{reading.reason.text}</p>
            <p
              className="mt-1 text-xs text-muted-foreground italic"
              data-testid="adjudication-reason-provenance"
            >
              {ADJUDICATION_REASON_IS_NEVER_THE_PERSONS}
            </p>
          </>
        )}
      </div>

      {/* Suppressed only for "nothing came out, so no statement was checked",
          which is the one case carrying no fact about a statement. Every other
          case is said here or nowhere. */}
      {reading.rescue.key !== "rescue-not-asked" && (
        <div
          data-testid="adjudication-rescue"
          data-rescue-key={reading.rescue.key}
          data-rescue-raw={reading.rescue.raw === null ? "null" : String(reading.rescue.raw)}
        >
          <p className="text-xs font-medium">{reading.rescue.label}</p>
          <p className="mt-1 text-xs text-muted-foreground">
            {reading.rescue.description}
          </p>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-1.5">
        {reading.ledgerStatus !== null && (
          <TermBadge
            term={reading.ledgerStatus}
            variant={
              reading.ledgerStatus.value === "admitted"
                ? "success"
                : reading.ledgerStatus.value === "quarantined"
                  ? "amber"
                  : reading.ledgerStatus.value === "rejected"
                    ? "danger"
                    : "slate"
            }
            testId="adjudication-status-now"
          />
        )}
        {/* Grounds are a proof or a person and the two must not look alike, so
            this badge is shown whenever the ledger sent one. */}
        {reading.quarantineReason !== null && (
          <TermBadge
            term={reading.quarantineReason}
            variant="outline"
            testId="adjudication-grounds"
          />
        )}
      </div>

      {reading.adjudicationId !== null && (
        <p
          className="font-mono text-[11px] text-muted-foreground"
          data-testid="adjudication-record-id"
        >
          Recorded as {reading.adjudicationId}
        </p>
      )}
    </div>
  )
}

export interface RowAdjudicationDialogProps {
  /**
   * Passed straight to the hook, which rejects when it is missing rather than
   * addressing a write to no case.
   */
  caseId: string | undefined
  row: LedgerTransaction
  open: boolean
  onClose: () => void
}

export function RowAdjudicationDialog({
  caseId,
  row,
  open,
  onClose,
}: RowAdjudicationDialogProps) {
  const [reason, setReason] = useState("")
  const adjudication = useRowAdjudication(caseId)

  const status = readLedgerStatus(row.ledger_status)
  const action = changeAvailableFor(status)
  const copy = action === null ? null : ACTION_COPY[action]

  const busy = adjudication.isPending
  const answer = adjudication.data
  const grounds = reason.trim()
  const canSubmit = grounds !== "" && action !== null && !busy && answer === undefined

  const close = () => {
    // Cleared on the way out rather than on the way in, so a dialog reopened
    // on a different row cannot show the previous row's answer for the frame
    // before anything replaces it.
    adjudication.reset()
    setReason("")
    onClose()
  }

  const submit = () => {
    if (action === null) return
    // The mutation reports its own failure through `error`; nothing is thrown
    // at the caller, so there is no rejection to handle here.
    adjudication.mutate({ transactionId: row.key, action, reason: grounds })
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        // A write in flight is not interruptible by dismissing the thing
        // watching it, so escape and the overlay are ignored while it runs.
        if (!next && !busy) close()
      }}
    >
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle data-testid="adjudication-title">
            {copy?.title ?? "This row cannot be changed from here"}
          </DialogTitle>
          <DialogDescription>
            {copy?.blurb ??
              "The ledger describes this row's standing in a word this screen is too old to read, and which change applies depends on that word. Nothing has been sent."}
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-[26rem] space-y-4 overflow-y-auto pr-1">
          <RowIdentity row={row} status={status} />

          {copy !== null && (
            <div className="space-y-1.5">
              <Label htmlFor="adjudication-reason-input">{copy.reasonLabel}</Label>
              <Textarea
                id="adjudication-reason-input"
                data-testid="adjudication-reason-input"
                rows={4}
                value={reason}
                disabled={busy || answer !== undefined}
                onChange={(e) => setReason(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">{copy.reasonHelp}</p>
            </div>
          )}

          {answer !== undefined && <AdjudicationAnswer reading={answer} />}

          {adjudication.error && (
            <p
              className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-xs"
              data-testid="adjudication-error"
            >
              {adjudication.error.message}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={close} disabled={busy}>
            {answer !== undefined ? "Done" : "Cancel"}
          </Button>
          {/* Gone once an answer has arrived, whatever the answer said: asking
              the same question again gets the same answer. A thrown error is
              different — nothing was decided — so the button stays for that. */}
          {answer === undefined && copy !== null && (
            <Button onClick={submit} disabled={!canSubmit} data-testid="adjudication-submit">
              {busy && <LoadingSpinner className="mr-1.5 size-3.5" />}
              {copy.submit}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
