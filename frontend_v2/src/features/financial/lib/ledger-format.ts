/**
 * Reading a relational ledger row for display.
 *
 * Two jobs, both of which exist because the ledger stores facts in the form
 * that keeps them exact rather than the form a person reads.
 *
 * **Money.** `amount_minor` is an integer count of minor units and a
 * magnitude: the sign lives in `direction`. Turning it into a figure needs the
 * currency's scale, which is not always two — JPY has none and BHD has three —
 * so dividing by a hundred is a money bug waiting for the first non-decimal
 * currency to arrive. `formatLedgerAmount` is the one place that scales, and
 * it scales by moving a decimal point through the digit string rather than by
 * dividing, so a large amount cannot lose its last cent to floating point.
 *
 * **Closed vocabularies.** `ledger_status`, `proof_class`, `direction`,
 * `ordering_date_source`, `quarantine_reason` and `extraction_layer` each come
 * off the wire as a bare string or int, because a backend one version ahead of
 * this build can send a member this build has never heard of. Rendering an
 * unrecognised member as blank would put an empty badge on the screen, which
 * reads as an answer rather than as the absence of one; rendering it raw would
 * pass a value off as a label. Each reader here narrows to a known member or
 * else says, in the label itself, that it does not know this one.
 *
 * Nothing here decides anything about a row. Whether a row counts toward a
 * total is settled on the backend, before it is ever read.
 */

import {
  DATE_SOURCES,
  LEDGER_STATUSES,
  PROOF_CLASSES,
  QUARANTINE_REASONS,
  TRANSACTION_DIRECTIONS,
  type DateSource,
  type LedgerStatus,
  type ProofClass,
  type QuarantineReason,
  type TransactionDirection,
} from "../api"

/**
 * A wire value narrowed to a member this build knows, or not.
 *
 * `value` is null exactly when this build does not recognise `raw`. `label`
 * and `description` are always safe to render: in the unrecognised case they
 * name the raw value and say it is unrecognised, so a reader can tell a
 * missing answer from an unknown one.
 */
export interface NarrowedTerm<T extends string> {
  value: T | null
  raw: string
  label: string
  description: string
}

export interface TermCopy {
  label: string
  description: string
}

/**
 * Exported for `ingest-format.ts`, which narrows the ingestion vocabularies
 * against the same rule. Shared rather than copied so that an unrecognised
 * word cannot be handled one way on the ledger screen and another way in the
 * dialog that puts rows on it.
 *
 * `source` names where the value came from, and only appears in the
 * unrecognised copy. It defaults to the ledger because that is where every
 * caller in this file reads from.
 */
export function narrow<T extends string>(
  raw: string,
  members: readonly T[],
  copy: Record<T, TermCopy>,
  source: string = "the ledger"
): NarrowedTerm<T> {
  const match = members.find((member) => member === raw)
  if (match === undefined) {
    return {
      value: null,
      raw,
      label: `Unrecognised (${raw})`,
      description:
        `This build does not recognise "${raw}". It came from ${source}, ` +
        `so it is a real value; this screen is older than the ledger that ` +
        `produced it.`,
    }
  }
  return { value: match, raw, ...copy[match] }
}

/* ------------------------------------------------------------------ *
 * Money
 * ------------------------------------------------------------------ */

/**
 * How many minor units make one major unit of `currency`, or null when the
 * code is not one this runtime can scale.
 *
 * The answer comes from the runtime's own currency data rather than from a
 * table kept here, because a table kept here is a table that goes stale.
 */
export function currencyMinorUnits(currency: string): number | null {
  const code = currency.trim().toUpperCase()
  const cached = minorUnitCache.get(code)
  if (cached !== undefined) return cached

  let digits: number | null
  try {
    digits =
      new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: code,
      }).resolvedOptions().maximumFractionDigits ?? null
  } catch {
    // A code that is not three ASCII letters. Malformed rather than merely
    // unfamiliar, and worth showing as such.
    digits = null
  }
  minorUnitCache.set(code, digits)
  return digits
}

const minorUnitCache = new Map<string, number | null>()

export interface LedgerAmountText {
  /**
   * The figure, grouped and pointed: "1,234.56". Grouping is fixed rather than
   * taken from the browser's locale, so the same row reads the same way on
   * every machine that opens the case.
   */
  text: string
  /** The ISO code as stored. A ledger shows "USD", not a dollar sign. */
  currency: string
  /**
   * False when `text` is a raw count of minor units rather than a figure,
   * which happens when the currency cannot be scaled or the stored amount is
   * not a whole number of minor units. A caller that renders an unscaled
   * amount without saying so is showing 123456 where 1,234.56 belongs.
   */
  scaled: boolean
}

function group(digits: string): string {
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",")
}

/**
 * Turn a stored minor-unit amount into a figure.
 *
 * The scaling is done by cutting the digit string, not by dividing, so the
 * result is exact for every amount the ledger can hold. A negative input keeps
 * its sign, though admitted rows do not carry one: `amount_minor` is a
 * magnitude and `running_balance_minor` is the field that can legitimately go
 * below zero.
 */
export function formatLedgerAmount(
  amountMinor: number,
  currency: string
): LedgerAmountText {
  const code = currency.trim().toUpperCase()
  const sign = amountMinor < 0 ? "-" : ""

  if (!Number.isSafeInteger(amountMinor)) {
    // Not a whole number of minor units, or too large to be one exactly.
    // Either way it cannot be scaled without inventing the part that is
    // missing, so it is shown as it arrived.
    return { text: String(amountMinor), currency: code, scaled: false }
  }

  const digits = String(Math.abs(amountMinor))
  const exponent = currencyMinorUnits(code)
  if (exponent === null) {
    return { text: sign + group(digits), currency: code, scaled: false }
  }
  if (exponent === 0) {
    return { text: sign + group(digits), currency: code, scaled: true }
  }

  const padded = digits.padStart(exponent + 1, "0")
  const cut = padded.length - exponent
  const text = `${sign}${group(padded.slice(0, cut))}.${padded.slice(cut)}`
  return { text, currency: code, scaled: true }
}

/* ------------------------------------------------------------------ *
 * Closed vocabularies
 * ------------------------------------------------------------------ */

const LEDGER_STATUS_COPY: Record<LedgerStatus, TermCopy> = {
  admitted: {
    label: "Admitted",
    description: "Counts toward totals and can be traced back to its source.",
  },
  quarantined: {
    label: "Quarantined",
    description:
      "Set aside, and left out of every total. The reason is recorded on the row.",
  },
  superseded: {
    label: "Superseded",
    description:
      "Replaced by a later row, which is the one that counts. Kept so the earlier reading stays visible.",
  },
  rejected: {
    label: "Rejected",
    description: "Not admitted to the ledger and never counted.",
  },
}

export function readLedgerStatus(raw: string): NarrowedTerm<LedgerStatus> {
  return narrow(raw, LEDGER_STATUSES, LEDGER_STATUS_COPY)
}

/**
 * The two changes a person can ask for against a stored row.
 *
 * Defined here rather than beside the mutation that sends it because two
 * separate screens name the change: the button on the row, and the button that
 * confirms it. A person who presses "Set aside" on a row and is then asked to
 * confirm something worded differently has been given two things to reconcile
 * at the moment they are deciding whether a figure counts.
 */
export type RowChange = "quarantine" | "release"

/**
 * The verb, in the words a person reads. One definition, used on the row and
 * on the dialog's submit button.
 */
export const ROW_CHANGE_LABELS: Record<RowChange, string> = {
  quarantine: "Set aside",
  release: "Let back in",
}

/**
 * Which change this row admits of, or null when the status cannot be read.
 *
 * `quarantined` is the only status with a release available; every other
 * readable one has a setting aside available, whether or not the ledger will
 * grant it when asked. That last part is deliberate: this says what may be
 * asked, not what will be allowed, and the ledger's refusal is an answer a
 * person is entitled to see rather than a button they were never offered.
 *
 * Null is not "no change is possible". It is "this build cannot read the
 * status, so it cannot say which change this is", and a screen must not turn
 * that into a silently absent button.
 */
export function changeAvailableFor(
  status: NarrowedTerm<LedgerStatus>
): RowChange | null {
  if (status.value === null) return null
  return status.value === "quarantined" ? "release" : "quarantine"
}

const PROOF_CLASS_COPY: Record<ProofClass, TermCopy> = {
  p0: {
    label: "P0",
    description:
      "Structured file that carries its own control totals, so the figures can be checked against what the bank published.",
  },
  p1: {
    label: "P1",
    description:
      "Structured file without control totals. The figures were read exactly, but the file states no total to check them against.",
  },
  p2: {
    label: "P2",
    description:
      "Statement document whose arithmetic closes against its own printed balances.",
  },
  p3: {
    label: "P3",
    description:
      "Statement document whose arithmetic does not close, or could not be tried.",
  },
  p4: {
    label: "P4",
    description:
      "A figure asserted somewhere other than a financial record. Never admitted to the ledger and never counted; useful only as corroboration.",
  },
}

/**
 * Proof class is computed at ingestion from the source format and the outcome
 * of the arithmetic. Nothing on this screen or any other can raise it.
 */
export function readProofClass(raw: string): NarrowedTerm<ProofClass> {
  return narrow(raw, PROOF_CLASSES, PROOF_CLASS_COPY)
}

const DIRECTION_COPY: Record<TransactionDirection, TermCopy> = {
  credit: { label: "Credit", description: "Money into the account." },
  debit: { label: "Debit", description: "Money out of the account." },
}

export function readDirection(raw: string): NarrowedTerm<TransactionDirection> {
  return narrow(raw, TRANSACTION_DIRECTIONS, DIRECTION_COPY)
}

const DATE_SOURCE_COPY: Record<DateSource, TermCopy> = {
  transaction: {
    label: "Transaction date",
    description: "Ordered by the date the statement gives for the movement itself.",
  },
  posted: {
    label: "Posted date",
    description: "Ordered by the date the movement reached the account.",
  },
  value: {
    label: "Value date",
    description: "Ordered by the date the money became available.",
  },
  effective: {
    label: "Effective date",
    description: "Ordered by the date the movement was made to take effect.",
  },
}

/**
 * A statement can print up to four dates for one movement. This says which one
 * the ledger sequenced by, so the choice can be reviewed rather than guessed
 * at.
 */
export function readDateSource(raw: string): NarrowedTerm<DateSource> {
  return narrow(raw, DATE_SOURCES, DATE_SOURCE_COPY)
}

const QUARANTINE_REASON_COPY: Record<QuarantineReason, TermCopy> = {
  balance_break: {
    label: "Balance break",
    description:
      "The statement's own running balance does not admit this row. The document contradicts it.",
  },
  unreadable_row: {
    label: "Unreadable row",
    description:
      "The amount, direction or date could not be read exactly, so the row cannot be summed without inventing the missing part.",
  },
  currency_mismatch: {
    label: "Currency mismatch",
    description:
      "Denominated differently from the period holding it. Adding it in would produce a number that means nothing.",
  },
  unexplained_delta: {
    label: "Unexplained delta",
    description:
      "The statement did not balance and no cause was found. The rows may each be right; what is not established is that they are all of them.",
  },
  adjudicated: {
    label: "Set aside by a person",
    description: "Someone decided, and the reasoning is on the record.",
  },
}

export function readQuarantineReason(
  raw: string
): NarrowedTerm<QuarantineReason> {
  return narrow(raw, QUARANTINE_REASONS, QUARANTINE_REASON_COPY)
}

/* ------------------------------------------------------------------ *
 * Quarantine grounds
 * ------------------------------------------------------------------ */

/**
 * Which of the two things established the grounds.
 *
 * `QuarantineBasis` on the backend puts it plainly: grounds are a proof or a
 * person, and nothing else. `from_proof` and the three failure constructors
 * produce the four computed members; `from_adjudication` is the only path to
 * `adjudicated`, and `quarantine_case_row` is explicit that a person cannot
 * type any of the others, because a class a person raised must not be mistaken
 * for one the arithmetic proved.
 *
 * That distinction is the whole reason this screen exists, so it is carried
 * here rather than left to be inferred from a label at each call site.
 */
const DECIDED_BY_PERSON: Record<QuarantineReason, boolean> = {
  balance_break: false,
  unreadable_row: false,
  currency_mismatch: false,
  unexplained_delta: false,
  adjudicated: true,
}

export interface QuarantineGrounds extends NarrowedTerm<QuarantineReason> {
  /**
   * Three-valued, and deliberately not a boolean. False means the ledger's own
   * checks established these grounds; null means this build cannot read the
   * member at all and so cannot say which of the two it was. Collapsing null
   * into false would report an unknown member as machine-established, which is
   * the more trusted of the two answers and the one it has not earned.
   */
  decidedByPerson: boolean | null
  /** Always safe to render. Says what kind of grounds these are, in words. */
  origin: string
}

/**
 * A quarantine reason, read together with what established it.
 *
 * The words a person gave are not here and cannot be: the ledger read carries
 * `quarantine_reason` and no detail field, and the actor-and-reason text built
 * by `QuarantineBasis.from_adjudication` is written to the `adjudications`
 * table, which this screen does not read. So the most this can say about an
 * adjudicated row is that a person decided it and that their reasoning is
 * recorded elsewhere. Saying more would be inventing it.
 */
export function readQuarantineGrounds(raw: string): QuarantineGrounds {
  const term = readQuarantineReason(raw)
  if (term.value === null) {
    return {
      ...term,
      decidedByPerson: null,
      origin:
        "This build cannot tell whether a person or one of the ledger's own " +
        "checks established these grounds, because it does not recognise them.",
    }
  }
  const decidedByPerson = DECIDED_BY_PERSON[term.value]
  return {
    ...term,
    decidedByPerson,
    origin: decidedByPerson
      ? "A person decided this. What they gave as their reason is on the " +
        "adjudication record and is not carried on the row."
      : "Established by the ledger's own checks against the source document, " +
        "not by anyone's judgement.",
  }
}

/* ------------------------------------------------------------------ *
 * Extraction layer
 * ------------------------------------------------------------------ */

export interface ExtractionLayerReading {
  /** Null when this build does not recognise the layer. */
  value: 0 | 1 | 2 | 3 | null
  raw: number
  label: string
  description: string
  /**
   * True for the marked fallback. A ledger built mostly from it is a ledger to
   * be explained, so a caller has grounds to draw attention to it.
   */
  isFallback: boolean
}

const EXTRACTION_LAYER_COPY: Record<0 | 1 | 2 | 3, TermCopy> = {
  0: {
    label: "Native",
    description:
      "Read straight out of a structured file that defines the field. Nothing was interpreted.",
  },
  1: {
    label: "Template",
    description:
      "Matched against a known statement layout that is version controlled.",
  },
  2: {
    label: "Structural",
    description:
      "Read from the page structure, with a model interpreting what the structure meant.",
  },
  3: {
    label: "Grounded model",
    description:
      "Read by a model with the source held alongside it. A marked fallback, not a normal path.",
  },
}

export function readExtractionLayer(raw: number): ExtractionLayerReading {
  if (raw === 0 || raw === 1 || raw === 2 || raw === 3) {
    return {
      value: raw,
      raw,
      ...EXTRACTION_LAYER_COPY[raw],
      isFallback: raw === 3,
    }
  }
  return {
    value: null,
    raw,
    label: `Unrecognised (${raw})`,
    description:
      `This build does not recognise layer ${raw}. It came from the ledger, ` +
      `so it is a real value; this screen is older than the ledger that ` +
      `produced it.`,
    isFallback: false,
  }
}
