import type { StatementDuplicateDisposition } from "./statement-duplicate"

// Plain-words summaries of statements the system set aside as copies of a
// retained statement, shown before the investigator opens anything.

/** Only a current "ignored" disposition is a copy; anything else is work. */
export function isCurrentCopy(
  disposition: StatementDuplicateDisposition | null | undefined
): disposition is StatementDuplicateDisposition {
  return (
    !!disposition && disposition.current && disposition.status === "ignored"
  )
}

/** "Copy of <file> p.3" for one statement. */
export function copyBadge(disposition: StatementDuplicateDisposition) {
  const retained = disposition.retained
  if (!retained) return "Copy of another statement"
  return `Copy of ${retained.filename} p.${retained.page_number}`
}

/** "a.pdf", "a.pdf and b.pdf", "a.pdf and 2 other files". */
export function retainedNames(names: string[]) {
  const unique = [...new Set(names.filter(Boolean))]
  if (!unique.length) return "another statement"
  if (unique.length === 1) return unique[0]
  if (unique.length === 2) return `${unique[0]} and ${unique[1]}`
  return `${unique[0]} and ${unique.length - 1} other files`
}

/**
 * One line per file: everything a copy → nothing to review; some copies →
 * "N of M are copies"; no copies → empty string.
 */
export function copyLine(copies: number, statements: number, names: string[]) {
  if (!copies || !statements) return ""
  const of = retainedNames(names)
  if (copies >= statements)
    return statements === 1
      ? `This statement is a copy of ${of} — nothing to review`
      : `All ${statements} statements are copies of ${of} — nothing to review`
  return `${copies} of ${statements} statements are copies of ${of}`
}

/** Copy summary for a file register entry (current ignored dispositions only). */
export function fileCopyLine(saved: {
  prepared_periods?: number
  ignored_periods: number
  duplicate_dispositions: { decision: StatementDuplicateDisposition }[]
}) {
  const copies = saved.duplicate_dispositions.filter(({ decision }) =>
    isCurrentCopy(decision)
  )
  const total = saved.prepared_periods ?? copies.length
  return copyLine(
    Math.min(copies.length, total),
    total,
    copies.map(({ decision }) => decision.retained?.filename ?? "")
  )
}
