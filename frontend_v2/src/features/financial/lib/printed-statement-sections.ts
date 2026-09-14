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
  columns: { header: PrintedCell | null; box: number[] | null }[]
  rows: {
    row: PrintedRow
    cells: (PrintedCell | undefined)[]
    parts?: PrintedCell[][]
  }[]
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
  /^(?:interest charged|(?:20\d{2} )?totals year-to-date|interest charge calculation)$/i
const numericText = (text: string) =>
  /^[+\-\s(]*[€£$]?\s*\d[\d,.]*\)?\s*-?$/.test(text.trim())
const signText = (text: string) => /^[+-]$/.test(text.trim())
const sameLine = (a: number[], b: number[]) =>
  Math.min(a[3], b[3]) > Math.max(a[1], b[1])

function printedColumns(headers: PrintedCell[], following: PrintedRow[]) {
  const columns: PrintedSection["columns"] = headers.map((header) => ({
    header,
    box: rect(header),
  }))
  // This printed layout has an unlabelled reference column between the date
  // and Item Description. Keep its heading blank, rather than inventing one
  // or placing the reference under Date. Require measured reference positions.
  if (
    headers.map(label).join("|") !== "trans date|item description|amount" ||
    columns.some((c) => !c.box)
  )
    return columns
  const [date, description, amount] = columns.map((c) => c.box!)
  const references: number[][] = []
  for (const row of following) {
    if (
      row.source_cells.some(
        (c) =>
          dates.has(label(c)) ||
          /^(?:fees|interest charged|\d{4} totals year-to-date)$/i.test(
            c.expected_text.trim()
          )
      )
    )
      break
    if (!["transaction", "unresolved"].includes(row.kind ?? "")) continue
    const values = row.source_cells.map((c) => ({ cell: c, box: rect(c) }))
    const rowDate = values.find(
      (v) => v.box && Math.abs(v.box[0] - date[0]) <= 3000
    )
    const rowAmount = values.find(
      (v) =>
        v.box &&
        Math.abs(v.box[2] - amount[2]) <= 15000 &&
        numericText(v.cell.expected_text)
    )
    if (
      !rowDate?.box ||
      !rowAmount?.box ||
      !sameLine(rowDate.box, rowAmount.box)
    )
      continue
    const candidates = values.filter(
      (v) =>
        v.box &&
        sameLine(v.box, rowDate.box!) &&
        v.box[0] > date[2] &&
        v.box[2] < description[0] &&
        /^[A-Z0-9 ]{12,30}$/.test(v.cell.expected_text.trim()) &&
        /\d/.test(v.cell.expected_text)
    )
    if (candidates.length === 1) references.push(candidates[0].box!)
  }
  if (
    references.length &&
    references.every((b) => Math.abs(b[0] - references[0][0]) <= 3000)
  ) {
    columns.splice(1, 0, {
      header: null,
      box: [
        Math.min(...references.map((b) => b[0])),
        date[1],
        Math.max(...references.map((b) => b[2])),
        date[3],
      ],
    })
  }
  return columns
}

function besideAmountSign(
  cell: PrintedCell,
  row: PrintedRow,
  header: PrintedCell | undefined
) {
  const box = rect(cell),
    headerBox = header && rect(header)
  if (!box || !headerBox || !signText(cell.expected_text)) return false
  return row.source_cells.some((other) => {
    const otherBox = rect(other)
    return (
      otherBox &&
      numericText(other.expected_text) &&
      sameLine(box, otherBox) &&
      Math.abs(otherBox[2] - headerBox[2]) <= 15000 &&
      ((box[0] >= otherBox[2] && box[0] - otherBox[2] <= 15000) ||
        (otherBox[0] >= box[2] && otherBox[0] - box[2] <= 15000))
    )
  })
}

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
          [
            "description",
            "item description",
            "details",
            "transaction details",
          ].includes(label(c))
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
          columns: printedColumns(headers, ordered.slice(i + 1)),
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
        if (
          /calculation|totals year-to-date/i.test(nonempty[0].expected_text)
        ) {
          active = null
          continue
        }
        active = {
          key: row.id,
          page: row.page_number,
          title: nonempty[0],
          titleRowId: row.id,
          headers: [],
          columns: [],
          rows: [],
        }
        sections.push(active)
        mark(row.id, nonempty[0])
        continue
      }
      const lastHeader = active.headers.at(-1)
      const lastHeaderBox = lastHeader && rect(lastHeader)
      const within = row.source_cells.filter((c) => {
        const box = rect(c)
        // A left-aligned amount can be wider than the word "Amount". Its
        // measured left edge still identifies the last printed column.
        const extendsAmountHeader =
          box &&
          lastHeader &&
          lastHeaderBox &&
          amounts.has(label(lastHeader)) &&
          numericText(c.expected_text) &&
          Math.abs(box[0] - lastHeaderBox[0]) <= 3000
        return (
          !bounds ||
          !box ||
          (box[0] >= bounds[0] - 3000 && box[2] <= bounds[1] + 3000) ||
          extendsAmountHeader ||
          (lastHeader &&
            amounts.has(label(lastHeader)) &&
            besideAmountSign(c, row, lastHeader))
        )
      })
      if (!within.some((c) => c.expected_text.trim())) continue
      if (!active.headers.length) {
        active.rows.push({ row, cells: within })
        within.forEach((c) => mark(row.id, c))
        continue
      }
      const mapped: (PrintedCell | undefined)[] = active.columns.map(
        () => undefined
      )
      const parts: PrintedCell[][] = active.columns.map(() => [])
      for (const cell of within) {
        const box = rect(cell)
        let column = active.columns.findIndex(
          (c) => c.header?.column_index === cell.column_index
        )
        if (box && active.columns.every((c) => c.box)) {
          // OCR can remove a date separator. A numeric reading in the printed
          // date position still belongs under Date, not under Amount.
          const dateColumn = active.columns.findIndex(
            (c, index) =>
              c.header &&
              dates.has(label(c.header)) &&
              Math.abs(box[0] - c.box![0]) <= 3000 &&
              box[2] < (active!.columns[index + 1]?.box?.[0] ?? Infinity)
          )
          const referenceColumn = active.columns.findIndex(
            (c) =>
              !c.header &&
              c.box &&
              box[0] >= c.box[0] - 1500 &&
              box[2] <= c.box[2] + 1500
          )
          // Amounts are right aligned. Preserve their printed column even when a total spans the date and description columns.
          const numeric =
            numericText(cell.expected_text) ||
            besideAmountSign(cell, row, lastHeader)
          if (dateColumn >= 0) column = dateColumn
          else if (referenceColumn >= 0) column = referenceColumn
          else if (numeric)
            column = active.columns.reduce(
              (best, c, j) =>
                c.header &&
                amounts.has(label(c.header)) &&
                (best < 0 ||
                  Math.abs(c.box![2] - box[2]) <
                    Math.abs(active!.columns[best].box![2] - box[2]))
                  ? j
                  : best,
              -1
            )
          else
            column = active.columns.reduce(
              (best, c, j) => (c.box![0] <= box[0] + 1500 ? j : best),
              0
            )
        }
        // Keep measured pieces of a description together, and a detached sign
        // beside its amount. Two amounts in one column remain a layout problem.
        if (column >= 0 && !mapped[column]) {
          mapped[column] = cell
          parts[column].push(cell)
          mark(row.id, cell)
        } else if (column >= 0 && box) {
          const previous = parts[column].at(-1)
          const previousBox = previous && rect(previous)
          const printedHeader = active.columns[column].header
          const amountColumn =
            printedHeader && amounts.has(label(printedHeader))
          const descriptionColumn =
            printedHeader &&
            [
              "description",
              "item description",
              "details",
              "transaction details",
            ].includes(label(printedHeader))
          const upperBound = active.columns[column + 1]?.box?.[0] ?? Infinity
          const signPair =
            previous &&
            parts[column].length === 1 &&
            ((signText(cell.expected_text) &&
              numericText(previous.expected_text)) ||
              (numericText(cell.expected_text) &&
                signText(previous.expected_text)))
          if (
            previousBox &&
            previousBox[2] <= box[0] &&
            sameLine(previousBox, box) &&
            ((descriptionColumn && box[2] < upperBound) ||
              (amountColumn && signPair && box[0] - previousBox[2] <= 15000))
          ) {
            parts[column].push(cell)
            mark(row.id, cell)
          }
        }
      }
      if (mapped.some(Boolean)) active.rows.push({ row, cells: mapped, parts })
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
