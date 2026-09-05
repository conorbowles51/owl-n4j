/**
 * Reading the answer to an attempt to change a ledger row's standing.
 *
 * `financialAPI.quarantineRow` and `.releaseRow` return one `RowAdjudication`
 * describing what became of the attempt. Turning that into something a person
 * can read is harder than it looks, for three reasons that are all about not
 * saying something untrue.
 *
 * **Almost nothing this endpoint says is an error.** Only a missing row and a
 * failed write leave the happy path; a refusal comes back as an ordinary
 * answer carrying the refusal. So the outcome is not a success flag to be
 * checked and discarded, it is the content. Every one of the six words it can
 * carry means something different about what is now true of the row, and this
 * module gives each of them a sentence.
 *
 * **`reason` is one field carrying four different things, and none of them is
 * what the person typed.** On a quarantine it is the system's own note about
 * whether removing the row balanced its statement. On a refusal it is why the
 * writers would not act. On an unchanged row it is why there was nothing to
 * do. On a release it is empty, because the words the person gave went to the
 * record rather than into this answer. A screen that labelled this field "your
 * reason" would put words in somebody's mouth, which is the one thing an
 * evidence log cannot do. `readAdjudicationReason` keys off the outcome so the
 * caller is told which of the four it is holding, and
 * `ADJUDICATION_REASON_IS_NEVER_THE_PERSONS` is the sentence that says so on
 * screen.
 *
 * **`rescues_period` has three values and they are not two.** `false` and
 * `null` say different things: one is "no statement was made to balance by
 * this", the other is "the question was asked and could not be answered".
 * Rendering them alike loses the distinction, and this answer is the only
 * place the fact appears at all -- it is deliberately not written to the
 * record, because an observation the system made must not end up filed as a
 * person's finding. If the screen drops it at the moment of the decision, it
 * is not anywhere.
 *
 * Narrowing goes through `narrow` in `ledger-format.ts`, so a word this build
 * has never heard of is handled here the way it is handled everywhere else:
 * named, marked unrecognised, never rendered blank.
 *
 * One thing this module deliberately does not do: re-narrow `ledger_status`
 * and `quarantine_reason` against a new provenance string. Both are copied
 * straight off the stored row by `_current` in `quarantine_row.py`, so "it
 * came from the ledger" is the true sentence for them and `readLedgerStatus`
 * and `readQuarantineReason` are reused unchanged. Only `outcome` is new: it
 * is produced by the write that was just attempted and never stored anywhere,
 * so it narrows against its own source string.
 */

import {
  ROW_ADJUDICATION_OUTCOMES,
  type LedgerStatus,
  type QuarantineReason,
  type RowAdjudication,
  type RowAdjudicationOutcome,
} from "../api"
import {
  narrow,
  readLedgerStatus,
  readQuarantineReason,
  type NarrowedTerm,
  type TermCopy,
} from "./ledger-format"
import type { Badge } from "@/components/ui/badge"
import type { ComponentProps } from "react"

type BadgeVariant = NonNullable<ComponentProps<typeof Badge>["variant"]>

/**
 * Where an outcome came from, for the unrecognised copy.
 *
 * Not "the ledger": an outcome is not stored anywhere and cannot be read back.
 * It is what one attempt to write came to, and it exists only in the answer to
 * that attempt.
 */
export const ADJUDICATION_SOURCE = "the record of the change you just asked for"

/**
 * Why none of the text in an adjudication answer is the words the person
 * typed.
 *
 * Held here as one string so the screen and the tests say the same thing, the
 * way `RUN_COUNTS_ARE_HISTORY` does for the counts on a run. A caller showing
 * `reason` shows this beside it.
 */
export const ADJUDICATION_REASON_IS_NEVER_THE_PERSONS =
  "The wording here is the system's, not yours. What you wrote goes on the " +
  "record against your name, where it stays readable for as long as the case " +
  "does."

/* ------------------------------------------------------------------ *
 * The outcome
 * ------------------------------------------------------------------ */

const OUTCOME_COPY: Record<RowAdjudicationOutcome, TermCopy> = {
  quarantined: {
    label: "Set aside",
    description:
      "The row is out of every total, search and money flow this case reports, and a decision naming who set it aside and why is on the record.",
  },
  released: {
    label: "Back in the ledger",
    description:
      "The row counts toward totals again. The setting aside was not deleted; the reversal is recorded after it, so the record holds both and who took each.",
  },
  unchanged: {
    label: "No change",
    description:
      "The row was already in the state this asked for, so nothing was written and nothing was added to the record.",
  },
  refused: {
    label: "Not done",
    description:
      "The change was not made, and the ledger said why. This is a statement about where the row stands now, not a fault: somebody may have acted on it since this screen was loaded.",
  },
  not_found: {
    label: "Row not found",
    description:
      "There is no such row in this case. A row belonging to a case you cannot see reads the same way, so asking cannot be used to find out what is in one.",
  },
  write_failed: {
    label: "Write failed",
    description:
      "Nothing was written. The attempt failed against the database and has been logged for someone to look at.",
  },
}

/**
 * Colours are shared with the ledger table on purpose. A row that is set aside
 * badges amber there, so the answer that set it aside badges amber here, and a
 * released row takes the colour `admitted` has. `warning` is not used for any
 * outcome because `LedgerTable` reserves it for "this build cannot read this
 * value", which is the case below.
 */
const OUTCOME_VARIANT: Record<RowAdjudicationOutcome, BadgeVariant> = {
  quarantined: "amber",
  released: "success",
  unchanged: "slate",
  refused: "danger",
  not_found: "destructive",
  write_failed: "destructive",
}

/** Reserved for "this build cannot read this value", matching `LedgerTable`. */
const UNRECOGNISED_VARIANT: BadgeVariant = "warning"

export interface OutcomeReading extends NarrowedTerm<RowAdjudicationOutcome> {
  variant: BadgeVariant
  /**
   * Whether this build's own reading of the word says the stored row moved.
   *
   * True for exactly the two outcomes that write, false for the four that do
   * not, and **null for a word this build cannot read** -- guessing either way
   * about an unknown outcome would either hide a change or claim one.
   *
   * This is not the same field as `RowAdjudication.applied`, which is the
   * backend's own derivation and arrives on the wire. They should always
   * agree; `readRowAdjudication` reports it when they do not.
   */
  changedTheRow: boolean | null
}

const CHANGES_THE_ROW: ReadonlySet<RowAdjudicationOutcome> =
  new Set<RowAdjudicationOutcome>(["quarantined", "released"])

export function readRowAdjudicationOutcome(raw: string): OutcomeReading {
  const term = narrow(
    raw,
    ROW_ADJUDICATION_OUTCOMES,
    OUTCOME_COPY,
    ADJUDICATION_SOURCE
  )
  if (term.value === null) {
    return { ...term, variant: UNRECOGNISED_VARIANT, changedTheRow: null }
  }
  return {
    ...term,
    variant: OUTCOME_VARIANT[term.value],
    changedTheRow: CHANGES_THE_ROW.has(term.value),
  }
}

/* ------------------------------------------------------------------ *
 * Whether the removal balanced a statement
 * ------------------------------------------------------------------ */

/**
 * Which of the four things `rescues_period` can be saying.
 *
 * Four and not three because the three stored values only mean what they mean
 * on a quarantine. On any other outcome nothing came out of the ledger, so
 * there was no removal to check and the field is empty for that reason rather
 * than for any of the other three.
 */
export type RescueKey =
  | "rescue-balanced"
  | "rescue-none"
  | "rescue-unknown"
  | "rescue-not-asked"

export interface RescueReading {
  key: RescueKey
  /** As it arrived, so a caller can show the distinction it is drawing. */
  raw: boolean | null
  label: string
  description: string
}

const RESCUE_COPY: Record<RescueKey, TermCopy> = {
  "rescue-balanced": {
    label: "The statement balances without this row",
    description:
      "Before this row came out, the statement's own opening and closing figures did not account for the movements listed on it, and this row accounts for exactly the difference. That it balances now is arithmetic rather than evidence: taking out the row that was the gap will always close the gap. It is a fact to weigh next to the grounds, not a finding on its own.",
  },
  "rescue-none": {
    label: "No statement was made to balance by this",
    description:
      "Taking this row out did not close a gap in a statement. That covers a statement that was already balancing, one that never printed the opening and closing figures the check needs, and a row that belongs to no statement period at all.",
  },
  "rescue-unknown": {
    label: "Could not be established",
    description:
      "The question was asked and could not be answered, because something on the statement period could not be worked with. This is not the same as no: nothing was established either way, and the row was set aside regardless, which is the right thing to do.",
  },
  "rescue-not-asked": {
    label: "Not asked",
    description:
      "Nothing came out of the ledger here, so there was no removal to check a statement against.",
  },
}

/**
 * What the answer says about whether setting this row aside balanced its
 * statement.
 *
 * Keyed off the outcome as well as the value, because the value alone is
 * ambiguous: `null` on a quarantine means the question could not be answered,
 * and `null` on a refusal means the question never arose.
 *
 * The order of the tests matters. `true` is taken first and taken at face
 * value whatever the outcome says, because it is a positive assertion the
 * backend made and this build does not know better. Anything that is neither
 * exactly `true` nor exactly `false` -- which the type forbids but the wire
 * does not -- falls through to "could not be established", which claims less
 * than the alternatives rather than more.
 */
export function readRescueOutcome(result: RowAdjudication): RescueReading {
  const raw = result.rescues_period
  const outcome = readRowAdjudicationOutcome(result.outcome)

  let key: RescueKey
  if (raw === true) {
    key = "rescue-balanced"
  } else if (outcome.value !== null && outcome.value !== "quarantined") {
    key = "rescue-not-asked"
  } else if (raw === false) {
    key = "rescue-none"
  } else {
    key = "rescue-unknown"
  }

  return { key, raw: raw === true || raw === false ? raw : null, ...RESCUE_COPY[key] }
}

/* ------------------------------------------------------------------ *
 * The overloaded reason
 * ------------------------------------------------------------------ */

/**
 * Which of its meanings the `reason` field is carrying.
 *
 * `not-carried` is a release, where the field is empty by design: the words
 * the person gave went onto the record, not into this answer.
 *
 * `unexpected` is the two outcomes the router turns into HTTP errors, so a
 * body carrying one of them means something upstream has changed. Shown
 * rather than swallowed.
 *
 * `unattributed` is an outcome this build cannot read. Text arrived, and what
 * it is a statement about is not established, so it must not be presented as
 * any of the others.
 */
export type ReasonKind =
  | "rescue-note"
  | "why-refused"
  | "why-unchanged"
  | "not-carried"
  | "unexpected"
  | "unattributed"

export interface ReasonReading {
  kind: ReasonKind
  /** Never empty, so a caller cannot render this text with nothing over it. */
  heading: string
  /** Null when the field carries nothing, which is normal on a release. */
  text: string | null
}

const REASON_HEADING: Record<ReasonKind, string> = {
  "rescue-note": "What the system noticed when this row came out",
  "why-refused": "Why this was not done",
  "why-unchanged": "Why there was nothing to do",
  "not-carried": "What you wrote is on the record, not here",
  unexpected: "This answer should not have arrived",
  unattributed: "This text cannot be attributed",
}

const REASON_KIND: Record<RowAdjudicationOutcome, ReasonKind> = {
  quarantined: "rescue-note",
  released: "not-carried",
  unchanged: "why-unchanged",
  refused: "why-refused",
  not_found: "unexpected",
  write_failed: "unexpected",
}

/**
 * The `reason` field with its meaning attached.
 *
 * The meaning comes from the outcome and nowhere else, because the text
 * itself gives no clue which of the four it is: a sentence about a statement
 * balancing and a sentence about why a write was refused are both just
 * sentences.
 */
export function readAdjudicationReason(result: RowAdjudication): ReasonReading {
  const outcome = readRowAdjudicationOutcome(result.outcome)
  const kind: ReasonKind =
    outcome.value === null ? "unattributed" : REASON_KIND[outcome.value]
  const text =
    typeof result.reason === "string" && result.reason.trim() !== ""
      ? result.reason
      : null
  return { kind, heading: REASON_HEADING[kind], text }
}

/* ------------------------------------------------------------------ *
 * The whole answer
 * ------------------------------------------------------------------ */

export interface RowAdjudicationReading {
  transactionId: string
  outcome: OutcomeReading
  /**
   * The backend's own answer to whether the row moved, as it arrived. Taken
   * from the wire rather than recomputed, because the backend is the thing
   * that knows what it wrote.
   */
  applied: boolean
  /**
   * True when the wire's `applied` and the outcome this build read from the
   * same answer contradict each other.
   *
   * They are derived from each other on the backend and cannot disagree there,
   * so a disagreement here means this build and that one do not mean the same
   * thing by a word. Worth surfacing rather than silently picking a winner:
   * either a change is being hidden or one is being claimed that never
   * happened, and both are the kind of thing that has to be visible.
   *
   * Always false for an outcome this build cannot read, where there is nothing
   * to compare against.
   */
  appliedDisagreesWithOutcome: boolean
  reason: ReasonReading
  rescue: RescueReading
  /** Null when the answer carried no status, which is a row that was not found. */
  ledgerStatus: NarrowedTerm<LedgerStatus> | null
  /**
   * Null both when the row is not held and when the answer carried no status
   * at all. A released row has its grounds nulled by the database's own rule,
   * so a row let back in is, on the row alone, indistinguishable from one
   * never set aside. The record is the only place that history exists.
   */
  quarantineReason: NarrowedTerm<QuarantineReason> | null
  /**
   * The decision this attempt appended, when it appended one.
   *
   * Null for every outcome that wrote nothing. That includes `unchanged`,
   * where an earlier decision by somebody else is what is holding the row:
   * this attempt did not make it, so no id is claimed for it here.
   */
  adjudicationId: string | null
}

/**
 * One adjudication answer, read whole.
 *
 * Composed rather than left to callers so that a screen cannot render the
 * outcome and quietly drop `rescues_period`, which is the only place that fact
 * is ever said.
 */
export function readRowAdjudication(
  result: RowAdjudication
): RowAdjudicationReading {
  const outcome = readRowAdjudicationOutcome(result.outcome)
  return {
    transactionId: result.transaction_id,
    outcome,
    applied: result.applied === true,
    appliedDisagreesWithOutcome:
      outcome.changedTheRow !== null &&
      outcome.changedTheRow !== (result.applied === true),
    reason: readAdjudicationReason(result),
    rescue: readRescueOutcome(result),
    ledgerStatus:
      result.ledger_status === null || result.ledger_status === undefined
        ? null
        : readLedgerStatus(result.ledger_status),
    quarantineReason:
      result.quarantine_reason === null || result.quarantine_reason === undefined
        ? null
        : readQuarantineReason(result.quarantine_reason),
    adjudicationId: result.adjudication_id ?? null,
  }
}
