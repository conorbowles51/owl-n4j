import type {
  SavedStatementFile,
  StatementFile,
} from "../hooks/use-statement-register"

const count = (n: number, one: string, many: string) =>
  `${n} ${n === 1 ? one : many}`

// Incomplete records are either missing values or complete values held until
// their statement reconciles. The card says which, and for which period.
export function incompleteSummary(missing: number, waiting: number) {
  return [
    missing
      ? `${count(missing, "incomplete record", "incomplete records")} to check`
      : "",
    waiting
      ? `${count(waiting, "completed record", "completed records")} waiting for the statement to reconcile`
      : "",
  ]
    .filter(Boolean)
    .join(" · ")
}

export type StatementFileCard = {
  /** Badge text shown on the file card. */
  label: string
  tone: "debit" | "info" | "review"
  /** The card shows a "not imported" state: read, nothing saved from it. */
  notImported: boolean
  /** Shown under the default "Needs action" filter. */
  needsAction: boolean
}

/**
 * The single source of a PDF statement card's state. The "Not imported" count
 * and the "Needs action" filter are computed from the same answer the card
 * shows, so the count always equals the cards that say so.
 */
export function statementFileCard(
  file: Pick<StatementFile, "status" | "id"> & { financial_removed?: boolean },
  saved: SavedStatementFile | undefined,
  {
    removed = false,
    statusLoaded,
    queued = false,
  }: { removed?: boolean; statusLoaded: boolean; queued?: boolean }
): StatementFileCard {
  const allPreparedIgnored =
    !!saved?.ignored_periods &&
    saved.ignored_periods === saved.prepared_periods &&
    !saved.current_transactions &&
    !saved.periods.length
  const tone: StatementFileCard["tone"] =
    file.status === "failed"
      ? "debit"
      : saved?.current_transactions ||
          saved?.periods.length ||
          saved?.wire_review_count
        ? "info"
        : "review"
  const checks =
    !!saved?.incomplete_count ||
    !!saved?.periods_with_checks ||
    !!saved?.available_periods
  const card = (label: string, notImported = false): StatementFileCard => ({
    label,
    tone,
    notImported,
    needsAction:
      !removed &&
      (notImported ||
        checks ||
        ["failed", "unprocessed"].includes(file.status)),
  })
  if (removed)
    return { label: "Removed from Financial", tone, notImported: false, needsAction: false }
  if (allPreparedIgnored)
    return {
      label: "Duplicate — left unimported",
      tone,
      notImported: false,
      needsAction: false,
    }
  if (saved?.wire_review_count)
    return card(
      `${saved.wire_review_count} saved wire ${saved.wire_review_count === 1 ? "review" : "reviews"}`
    )
  if (saved?.incomplete_count)
    return card(
      `${count(saved.current_transactions, "usable transaction", "usable transactions")} · ${incompleteSummary(saved.incomplete_count - saved.awaiting_reconciliation_count, saved.awaiting_reconciliation_count)}`
    )
  if (saved?.periods.length && !saved.current_transactions)
    return card(
      `Statement saved · ${saved.periods.length} recorded ${saved.periods.length === 1 ? "period" : "periods"} · no payments`
    )
  if (saved?.same_pdf_saved_file_ids.length)
    // This copy asks to be reviewed against the saved one.
    return { ...card("Same PDF has saved records · review this copy"), needsAction: true }
  if (saved && (saved.current_transactions || saved.periods.length))
    return card(
      `${count(saved.current_transactions, "imported payment", "imported payments")} · ${saved.periods.length} recorded ${saved.periods.length === 1 ? "period" : "periods"}`
    )
  if (saved?.available_periods)
    return card(
      `${count(saved.available_periods, "statement", "statements")} ready to save · not saved yet`,
      true
    )
  if (file.status === "processed") {
    if (!statusLoaded) return card("Ready to open")
    if (saved?.empty_reading)
      return card(`Not imported · ${saved.empty_reading.message}`, true)
    return card("Not imported · PDF read · open review to check and import", true)
  }
  if (file.status === "unprocessed" && queued)
    return card("Reading queued — waiting for progress")
  return card(file.status)
}
