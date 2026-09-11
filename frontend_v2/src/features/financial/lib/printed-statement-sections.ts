export type PrintedCell = {
  column_index: number
  expected_text: string
  locator: unknown
}
export type PrintedRow = {
  id: string
  page_number: number
  table_index: number
  row_index: number
  source_cells: PrintedCell[]
  kind?: string
  issues?: string[]
}
export type PrintedSection = {
  key: string
  page: number
  title: PrintedCell | null
  titleRowId: string
  headers: PrintedCell[]
  rows: { row: PrintedRow; cells: (PrintedCell | undefined)[] }[]
}
function rect(cell: PrintedCell) {
  const value = (cell.locator as { rect?: unknown })?.rect
  return Array.isArray(value) &&
    value.length === 4 &&
    value.every((v) => typeof v === "number" && Number.isFinite(v))
    ? (value as number[])
    : null
}
const label = (cell: PrintedCell) => cell.expected_text.trim().toLowerCase()
const dates = new Set([
  "date",
  "transaction date",
  "trans date",
  "post date",
  "posting date",
  "value date",
  "booking date",
])
const amounts = new Set([
  "amount",
  "credit",
  "credits",
  "debit",
  "debits",
  "money in",
  "money out",
  "paid in",
  "paid out",
  "balance",
  "running balance",
])
const heading =
  /^(?:interest charged|totals year-to-date|interest charge calculation)$/i

// Layout only: use printed headers and source positions. Never decide which rows to import here.
export function printedStatementSections(rows: PrintedRow[]) {
  const sections: PrintedSection[] = []
  const represented = new Set<string>()
  const mark = (rowId: string, cell: PrintedCell) =>
    represented.add(`${rowId}:${cell.column_index}`)
  const tables = new Map<string, PrintedRow[]>()
  rows.forEach((row) => {
    const key = `${row.page_number}:${row.table_index}`
    tables.set(key, [...(tables.get(key) ?? []), row])
  })
  for (const table of tables.values()) {
    const ordered = [...table].sort((a, b) => a.row_index - b.row_index)
    let active: PrintedSection | null = null
    let bounds: [number, number] | null = null
    for (let i = 0; i < ordered.length; i++) {
      const row = ordered[i]
      const headers = row.source_cells.filter(
        (c) =>
          dates.has(label(c)) ||
          amounts.has(label(c)) ||
          ["description", "details", "transaction details"].includes(label(c))
      )
      const isHeader =
        headers.some((c) => dates.has(label(c))) &&
        headers.some((c) => amounts.has(label(c)))
      if (isHeader) {
        const positions = headers.map(rect)
        bounds = positions.every(Boolean)
          ? [
              Math.min(...positions.map((r) => r![0])),
              Math.max(...positions.map((r) => r![2])),
            ]
          : null
        const previous = ordered[i - 1]
        const titleCells =
          previous?.source_cells.filter(
            (c) =>
              c.expected_text.trim() &&
              (!bounds ||
                !rect(c) ||
                (rect(c)![0] >= bounds[0] - 3000 &&
                  rect(c)![2] <= bounds[1] + 3000))
          ) ?? []
        const title =
          titleCells.length === 1 &&
          !/[€£$]|\d[,.]\d{2}\b/.test(titleCells[0].expected_text)
            ? titleCells[0]
            : null
        active = {
          key: row.id,
          page: row.page_number,
          title,
          titleRowId: previous?.id ?? row.id,
          headers,
          rows: [],
        }
        sections.push(active)
        headers.forEach((c) => mark(row.id, c))
        if (title) mark(previous.id, title)
        continue
      }
      if (!active) continue
      // The heading immediately before the next header belongs to that section, not this table.
      const next = ordered[i + 1]?.source_cells ?? []
      if (
        row.source_cells.filter((c) => c.expected_text.trim()).length === 1 &&
        next.some((c) => dates.has(label(c))) &&
        next.some((c) => amounts.has(label(c))) &&
        !/[€£$]|\d[,.]\d{2}\b/.test(row.source_cells[0].expected_text)
      ) {
        active = null
        continue
      }
      const nonempty = row.source_cells.filter((c) => c.expected_text.trim())
      if (
        nonempty.length === 1 &&
        heading.test(nonempty[0].expected_text.trim())
      ) {
        if (/calculation/i.test(nonempty[0].expected_text)) {
          active = null
          continue
        }
        active = {
          key: row.id,
          page: row.page_number,
          title: nonempty[0],
          titleRowId: row.id,
          headers: [],
          rows: [],
        }
        sections.push(active)
        mark(row.id, nonempty[0])
        continue
      }
      const within = row.source_cells.filter(
        (c) =>
          !bounds ||
          !rect(c) ||
          (rect(c)![0] >= bounds[0] - 3000 && rect(c)![2] <= bounds[1] + 3000)
      )
      if (!within.some((c) => c.expected_text.trim())) continue
      if (!active.headers.length) {
        active.rows.push({ row, cells: within })
        within.forEach((c) => mark(row.id, c))
        continue
      }
      const mapped: (PrintedCell | undefined)[] = active.headers.map(
        () => undefined
      )
      for (const cell of within) {
        const box = rect(cell)
        let column = active.headers.findIndex(
          (h) => h.column_index === cell.column_index
        )
        if (box && active.headers.every((h) => rect(h))) {
          // Amounts are right aligned. Preserve their printed column even when a total spans the date and description columns.
          const numeric = /^[+\-\s(]*[€£$]?\s*\d[\d,.]*\)?$/.test(
            cell.expected_text.trim()
          )
          if (numeric)
            column = active.headers.reduce(
              (best, h, j) =>
                amounts.has(label(h)) &&
                (best < 0 ||
                  Math.abs(rect(h)![2] - box[2]) <
                    Math.abs(rect(active!.headers[best])![2] - box[2]))
                  ? j
                  : best,
              -1
            )
          else
            column = active.headers.reduce(
              (best, h, j) => (rect(h)![0] <= box[0] + 1500 ? j : best),
              0
            )
        }
        // A collision means that layout was not recovered confidently. Leave that cell in additional text for inspection.
        if (column >= 0 && !mapped[column]) {
          mapped[column] = cell
          mark(row.id, cell)
        }
      }
      if (mapped.some(Boolean)) active.rows.push({ row, cells: mapped })
    }
  }
  const remaining = rows
    .map((row) => ({
      ...row,
      source_cells: row.source_cells.filter(
        (c) =>
          c.expected_text.trim() &&
          !represented.has(`${row.id}:${c.column_index}`)
      ),
    }))
    .filter((row) => row.source_cells.length)
  return { sections, remaining }
}
