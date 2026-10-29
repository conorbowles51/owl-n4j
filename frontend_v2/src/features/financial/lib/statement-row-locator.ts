import { readLocator } from "./locator"

// The navigation highlight covers only measured cells on the same source page.
// It is a display aid; the individual stored field locations remain unchanged.
export function statementRowLocator(
  row:
    | {
        source_cells: { locator: unknown }[]
        value_sources?: Record<string, { source_cell: { locator: unknown } }>
      }
    | undefined,
  page: number
) {
  const cells = [
    ...(row?.source_cells ?? []),
    ...Object.values(row?.value_sources ?? {}).map(
      (value) => value.source_cell
    ),
  ]
  const rectangles = cells.flatMap((cell) => {
    const reading = readLocator(cell.locator)
    return reading.ok &&
      reading.locator.kind === "page_rectangle" &&
      reading.locator.page === page
      ? [reading.locator.rectangle]
      : []
  })
  const first = rectangles[0]
  if (
    !first ||
    rectangles.some(
      (rect) =>
        rect.pageWidth !== first.pageWidth ||
        rect.pageHeight !== first.pageHeight
    )
  )
    return { kind: "page_only", page }
  return {
    kind: "page_rectangle",
    page,
    rect: [
      Math.min(...rectangles.map((r) => r.x0)),
      Math.min(...rectangles.map((r) => r.y0)),
      Math.max(...rectangles.map((r) => r.x1)),
      Math.max(...rectangles.map((r) => r.y1)),
    ],
    page_size: [first.pageWidth, first.pageHeight],
    units: "millipoints",
    space: "pdf_displayed",
  }
}

type ProblemRow = {
  id: string
  kind: string
  page_number: number
  fields: { balance_column?: string | null } & Record<string, unknown>
  source_cells: { column_index: number | string; locator: unknown }[]
  value_sources?: Record<string, { source_cell: { locator: unknown } }> | null
}

/** Where a printed balance or total is drawn: its balance cell, else its page. */
export function balanceCellLocator(original: ProblemRow): unknown {
  return (
    original.value_sources?.balance?.source_cell.locator ??
    original.source_cells.find((cell) => String(cell.column_index) === original.fields.balance_column)?.locator ?? {
      kind: "page_only",
      page: original.page_number,
    }
  )
}

/**
 * The highlight the statement review opens a problem row with (its openInlineRow
 * and reviewRow): a printed total at its balance cell, a row without measured
 * cells at its first cell or page, any other row across its measured cells.
 */
export function problemRowLocator(original: ProblemRow): unknown {
  if (!original.source_cells.length && !original.id.startsWith("manual:") && original.kind !== "statement_total")
    return original.source_cells[0]?.locator ?? { kind: "page_only", page: original.page_number }
  return original.kind === "statement_total"
    ? balanceCellLocator(original)
    : statementRowLocator(original as Parameters<typeof statementRowLocator>[0], original.page_number)
}
