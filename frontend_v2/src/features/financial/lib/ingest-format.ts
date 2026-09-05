/**
 * The words the precheck and ingest endpoints answer with, in English.
 *
 * Neither endpoint has a success path and an error path. Both answer with one
 * word out of a closed set, and nearly every value arrives as a 200 because it
 * is a fact about the evidence rather than a fault. So this module has no
 * concept of failure either: it turns each word into a label, a sentence
 * saying what it means for the file in front of the reader, and a badge
 * colour. Whether a given outcome should stop the reader is
 * `wouldStore`/`didStore`, not the colour.
 *
 * Every member of both vocabularies is spelled out in the copy tables below.
 * That is not thoroughness for its own sake. `Badge` falls through to its
 * `default` variant, a loud filled primary, for any key a variant map does not
 * carry, so an outcome missing from `INGEST_OUTCOME_VARIANT` would not fail
 * loudly; it would render as though it were the most important thing on the
 * screen. `Record<IngestOutcome, ...>` makes the compiler the thing that
 * notices instead.
 *
 * Narrowing goes through `ledger-format.ts` rather than being repeated here,
 * so a word this build has never heard of is handled the same way wherever it
 * turns up.
 */

import {
  INGEST_OUTCOMES,
  PRECHECK_OUTCOMES,
  type IngestOutcome,
  type PrecheckOutcome,
} from "../api"
import { narrow, type NarrowedTerm, type TermCopy } from "./ledger-format"
import type { Badge } from "@/components/ui/badge"
import type { ComponentProps } from "react"

type BadgeVariant = NonNullable<ComponentProps<typeof Badge>["variant"]>

/* ------------------------------------------------------------------ *
 * Precheck
 * ------------------------------------------------------------------ */

const PRECHECK_OUTCOME_COPY: Record<PrecheckOutcome, TermCopy> = {
  readable: {
    label: "Can be read",
    description:
      "The file was opened and its rows were read. What it holds is set out below, and nothing has been stored yet.",
  },
  unrecognised: {
    label: "Not a bank file",
    description:
      "Nothing in this file matches the shape of a bank record. It may still be worth processing as a document.",
  },
  ambiguous: {
    label: "Unclear format",
    description:
      "The file matches more than one bank format, so there is no single correct way to read it. Sending it would risk figures read under the wrong rules.",
  },
  out_of_window: {
    label: "Outside the date range",
    description:
      "The file prints years with two digits, and no reading of them falls inside the range given. Widen the range if the material is older or newer than expected.",
  },
  unattributable: {
    label: "Rows without an account",
    description:
      "Some rows name an account the file never introduces, so there is no way to say whose money moved. Those rows are listed below.",
  },
  unreadable: {
    label: "Could not be read",
    description:
      "The file could not be opened, or it stopped part way through. It may be damaged or only partly transferred.",
  },
  not_found: {
    label: "Not available",
    description: "This file is not in this case, or is no longer stored.",
  },
}

export function readPrecheckOutcome(raw: string): NarrowedTerm<PrecheckOutcome> {
  return narrow(raw, PRECHECK_OUTCOMES, PRECHECK_OUTCOME_COPY, "the reading")
}

export const PRECHECK_OUTCOME_VARIANT: Record<PrecheckOutcome, BadgeVariant> = {
  readable: "success",
  unrecognised: "slate",
  ambiguous: "warning",
  out_of_window: "warning",
  unattributable: "warning",
  unreadable: "danger",
  not_found: "danger",
}

/* ------------------------------------------------------------------ *
 * Ingest
 * ------------------------------------------------------------------ */

const INGEST_OUTCOME_COPY: Record<IngestOutcome, TermCopy> = {
  stored: {
    label: "Added to the ledger",
    description:
      "The rows are in the ledger and can be totalled, traced back to this file, and reviewed.",
  },
  already_ingested: {
    label: "Already in the ledger",
    description:
      "This case already holds the rows from this file. Nothing was added, so no figure has been counted twice.",
  },
  not_found: {
    label: "Not available",
    description: "This file is not in this case, or is no longer stored.",
  },
  unrecognised: {
    label: "Not a bank file",
    description:
      "Nothing in this file matches the shape of a bank record. It may still be worth processing as a document.",
  },
  ambiguous: {
    label: "Unclear format",
    description:
      "The file matches more than one bank format, so there is no single correct way to read it. Nothing was stored.",
  },
  out_of_window: {
    label: "Outside the date range",
    description:
      "The file prints years with two digits, and no reading of them falls inside the range given. Widen the range if the material is older or newer than expected.",
  },
  unreadable: {
    label: "Could not be read",
    description:
      "The file could not be opened, or it stopped part way through. It may be damaged or only partly transferred.",
  },
  undescribable: {
    label: "Accounts unclear",
    description:
      "The rows were read, but the accounts they belong to could not be set out well enough to file them against. Nothing was stored.",
  },
  unattributable: {
    label: "Rows without an account",
    description:
      "Some rows name an account the file never introduces, so there is no way to say whose money moved. Nothing was stored, because a partial statement counted as a whole one is worse than none.",
  },
  contradictory_period: {
    label: "Conflicts with a statement already held",
    description:
      "This file covers a period this case already has, and the two disagree. Both readings cannot be true, so nothing was stored until it is settled which is right.",
  },
  refused: {
    label: "Held back",
    description:
      "The rows were read but not admitted, because something about them would not stand up. The reason is given below.",
  },
  write_failed: {
    label: "Could not be saved",
    description:
      "The reading finished but the rows could not be written. Nothing was stored and nothing was half stored. This one is worth reporting.",
  },
}

export function readIngestOutcome(raw: string): NarrowedTerm<IngestOutcome> {
  return narrow(raw, INGEST_OUTCOMES, INGEST_OUTCOME_COPY, "the ledger")
}

export const INGEST_OUTCOME_VARIANT: Record<IngestOutcome, BadgeVariant> = {
  stored: "success",
  already_ingested: "info",
  not_found: "danger",
  unrecognised: "slate",
  ambiguous: "warning",
  out_of_window: "warning",
  unreadable: "danger",
  undescribable: "warning",
  unattributable: "warning",
  contradictory_period: "warning",
  refused: "warning",
  write_failed: "danger",
}

/* ------------------------------------------------------------------ *
 * Reading the answers
 * ------------------------------------------------------------------ */

/**
 * The badge for an outcome, fail-closed on a word this build does not know.
 *
 * An unrecognised outcome gets `outline` rather than the map's fallback,
 * because the fallback is `default` and would shout. It is paired with copy
 * that says the word was not recognised, so the quiet badge is not the whole
 * of what the reader is told.
 */
export function precheckVariant(term: NarrowedTerm<PrecheckOutcome>): BadgeVariant {
  return term.value === null ? "outline" : PRECHECK_OUTCOME_VARIANT[term.value]
}

export function ingestVariant(term: NarrowedTerm<IngestOutcome>): BadgeVariant {
  return term.value === null ? "outline" : INGEST_OUTCOME_VARIANT[term.value]
}

/**
 * Whether the reading found something worth offering to store.
 *
 * Taken from the endpoint's own `would_ingest` rather than recomputed from the
 * outcome word, so that a build older than the endpoint cannot decide to
 * offer a write the endpoint would refuse. The outcome word is what gets
 * explained to the reader; this is what governs the button.
 */
export function wouldStore(precheck: { would_ingest: boolean }): boolean {
  return precheck.would_ingest
}

/**
 * Whether the write happened. Read from `stored` for the same reason.
 *
 * Note that this is narrower than "nothing went wrong": `already_ingested` is
 * a good answer and reports `stored: false`, because this ingest stored
 * nothing even though the case holds the rows.
 */
export function didStore(ingestion: { stored: boolean }): boolean {
  return ingestion.stored
}

/**
 * A period's dates as one phrase, or null when the file printed neither.
 *
 * A statement missing one end is shown with the end it has and the word
 * "onwards" or "up to", rather than a blank standing in for a date. A blank
 * reads as though the period were open when in fact it was never printed.
 */
export function formatPeriodRange(
  start: string | null,
  end: string | null
): string | null {
  if (start && end) return `${start} to ${end}`
  if (start) return `${start} onwards`
  if (end) return `up to ${end}`
  return null
}

/**
 * How an account identifies itself, for a list a person reads down.
 *
 * `identified: false` does not mean the file printed no account number, so the
 * printed identifier is preferred over the internal key whenever there is one.
 * Falling back to the key rather than to "unknown" keeps the rows in the list
 * distinguishable from each other, which is the point of the line.
 */
export function accountLabel(account: {
  identifier_as_printed: string | null
  account_key: string | null
  holder_name: string | null
}): string {
  const identifier = account.identifier_as_printed ?? account.account_key
  if (identifier && account.holder_name) return `${identifier} (${account.holder_name})`
  if (identifier) return identifier
  if (account.holder_name) return account.holder_name
  return "Account not named in the file"
}
